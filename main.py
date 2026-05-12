# -*- coding: utf-8 -*-
"""
舆情分析助手 — A2A Server 入口
基于 A2A 协议提供知乎舆情分析能力

启动: python main.py
"""

import os
import json
import hashlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from searcher import ZhihuSearcher
from analyzer import SentimentAnalyzer
from wordcloud_gen import WordCloudGenerator
from formatter import ReportFormatter
from utils import log, SimpleCache

# 加载环境变量
load_dotenv()

# ============ 缓存 ============
_cache = SimpleCache(ttl_seconds=300)


# ============ 生命周期 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的生命周期管理"""
    log.info("舆情分析助手服务启动中...")
    log.info(f"LLM模式: {bool(os.getenv('OPENAI_API_KEY'))}")
    yield
    log.info("舆情分析助手服务关闭")


app = FastAPI(
    title="舆情分析助手",
    description="基于 A2A 协议的知乎舆情智能分析 Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 请求/响应模型 ============

class AnalyzeRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    limit: int = Field(20, ge=5, le=100)
    use_mock: bool = False
    force_refresh: bool = False  # 跳过缓存

    class Config:
        json_schema_extra = {
            "example": {"keyword": "AI编程", "limit": 20, "use_mock": True}
        }


class AnalyzeResponse(BaseModel):
    keyword: str
    total_answers: int
    sentiment: dict
    viewpoints: list
    keywords: list
    report: str
    report_markdown: str
    cached: bool = False


class A2ACard(BaseModel):
    """A2A Agent Card"""
    name: str = "sentiment-analysis-assistant"
    description: str = "知乎话题舆情智能分析 Agent，支持情绪分布、观点提取、关键词分析"
    url: str = ""
    version: str = "1.0.0"
    capabilities: dict = {"streaming": False, "pushNotifications": False}
    skills: list = [{
        "id": "analyze_sentiment",
        "name": "舆情分析",
        "description": "分析指定话题在知乎上的舆论倾向，包括情绪分布、代表性观点、高频关键词",
    }]


class A2ATaskRequest(BaseModel):
    id: str = ""
    sessionId: str = ""
    message: dict = {}


class A2ATaskResponse(BaseModel):
    id: str
    status: dict
    artifacts: list = []


# ============ 全局实例 ============

searcher = ZhihuSearcher()
analyzer = SentimentAnalyzer()
wc_generator = WordCloudGenerator()
formatter = ReportFormatter()


# ============ API 路由 ============

@app.get("/")
async def root():
    return {
        "service": "舆情分析助手",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "sentiment-analysis-assistant",
        "cache_size": _cache.size,
        "llm_mode": str(analyzer.use_llm),
    }


@app.get("/.well-known/agent.json")
async def agent_card():
    """A2A Agent Card — Agent 发现入口"""
    card = A2ACard()
    card.url = os.getenv("AGENT_URL", "http://localhost:8000")
    return card.model_dump()


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    """核心分析接口"""
    keyword = req.keyword.strip()

    # 缓存检查
    cache_key = _make_cache_key(keyword, req.use_mock)
    if not req.force_refresh:
        cached = _cache.get(cache_key)
        if cached:
            log.info(f"缓存命中: {keyword}")
            cached["cached"] = True
            return cached

    # 1. 搜索内容
    log.info(f"开始分析: {keyword}")
    if req.use_mock:
        search_result = await searcher.search_mock(keyword)
    else:
        search_result = await searcher.search(keyword)

    if not search_result.answers:
        search_result = await searcher.search_mock(keyword)

    # 2. 情绪分析
    analysis_result = analyzer.analyze(search_result.answers, keyword)

    # 3. 格式化报告
    report_text = formatter.format_text(analysis_result)
    report_markdown = formatter.format_markdown(analysis_result)
    json_result = analysis_result.to_dict()

    # 4. 构建响应
    response = AnalyzeResponse(
        keyword=keyword,
        total_answers=json_result["total_answers"],
        sentiment=json_result["sentiment"],
        viewpoints=json_result["viewpoints"],
        keywords=json_result["keywords"],
        report=report_text,
        report_markdown=report_markdown,
        cached=False,
    )

    # 5. 写入缓存
    _cache.set(cache_key, response.model_dump())
    return response


@app.post("/api/a2a/task")
async def a2a_task(req: A2ATaskRequest):
    """A2A 协议任务接口"""
    # 从 A2A 消息中提取关键词
    keyword = ""
    try:
        for part in req.message.get("parts", []):
            if part.get("type") == "text":
                keyword = part.get("text", "").strip()
                break
    except Exception:
        pass

    if not keyword:
        return A2ATaskResponse(
            id=req.id,
            status={"state": "failed", "message": "未提供分析关键词"},
        )

    try:
        search_result = await searcher.search(keyword)
        if not search_result.answers:
            search_result = await searcher.search_mock(keyword)

        analysis_result = analyzer.analyze(search_result.answers, keyword)

        return A2ATaskResponse(
            id=req.id,
            status={"state": "completed"},
            artifacts=[
                {
                    "name": "sentiment_report",
                    "type": "text/markdown",
                    "content": formatter.format_markdown(analysis_result),
                },
                {
                    "name": "sentiment_data",
                    "type": "application/json",
                    "content": json.dumps(analysis_result.to_dict(), ensure_ascii=False),
                },
            ],
        )

    except Exception as e:
        log.error(f"A2A 任务失败: {e}")
        return A2ATaskResponse(
            id=req.id,
            status={"state": "failed", "message": str(e)},
        )


@app.get("/api/wordcloud")
async def generate_wordcloud(
    keyword: str = Query(..., min_length=1),
    use_mock: bool = True,
):
    """生成词云图片"""
    if use_mock:
        search_result = await searcher.search_mock(keyword)
    else:
        search_result = await searcher.search(keyword)

    if not search_result.answers:
        search_result = await searcher.search_mock(keyword)

    analysis_result = analyzer.analyze(search_result.answers, keyword)

    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    wc_path = os.path.join(output_dir, f"wordcloud_{keyword}.png")
    wc_generator.generate(analysis_result.keywords, wc_path)

    chart_path = os.path.join(output_dir, f"sentiment_{keyword}.png")
    wc_generator.generate_sentiment_chart(analysis_result.sentiment, chart_path)

    return {
        "keyword": keyword,
        "wordcloud": wc_path if os.path.exists(wc_path) else None,
        "sentiment_chart": chart_path if os.path.exists(chart_path) else None,
        "sentiment": analysis_result.to_dict()["sentiment"],
    }


@app.post("/api/cache/clear")
async def clear_cache():
    """清除缓存"""
    size = _cache.size
    _cache.clear()
    log.info(f"缓存已清除，清理了 {size} 条")
    return {"cleared": size}


# ============ 工具函数 ============

def _make_cache_key(keyword: str, use_mock: bool) -> str:
    raw = f"{keyword}:{use_mock}".encode("utf-8")
    return hashlib.md5(raw).hexdigest()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("A2A_PORT", 8000))
    log.info(f"服务启动在 http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")