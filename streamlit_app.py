# -*- coding: utf-8 -*-
"""
知乎舆情分析助手 — Streamlit Web 应用
知乎黑客松参赛作品

启动: streamlit run streamlit_app.py
"""

import streamlit as st
import asyncio
import os
import sys
import json
import base64
import time

# 可选依赖：安全导入
try:
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# 确保可以 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from searcher import ZhihuSearcher, ZhihuAnswer, SearchResult
from analyzer import SentimentAnalyzer, AnalysisResult, SentimentResult, Viewpoint
from wordcloud_gen import WordCloudGenerator
from formatter import ReportFormatter
from utils import log

# ============ 动态热榜获取 ============

@st.cache_data(ttl=1200)
def fetch_zhihu_hot() -> list:
    """
    获取知乎热榜前十话题（使用 api.zhihu.com 公开接口，无需认证），缓存 20 分钟。
    失败返回空列表，由调用方降级处理。
    """
    try:
        import httpx
    except ImportError:
        st.error("httpx 未安装，请运行: pip install httpx")
        return []
    
    # 使用 api.zhihu.com 公开接口，无需 access_key 认证
    url = "https://api.zhihu.com/topstory/hot-list"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36"
    }
    params = {"limit": 10, "reverse_order": 0}
    
    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        topics = []
        for item in data.get("data", [])[:10]:
            target = item.get("target", {})
            title = target.get("title", "")
            if title:
                topics.append(title)
        return topics if topics else []
    except Exception as e:
        try:
            st.warning(f"获取热榜失败：{e}")
        except Exception:
            pass
        return []


# ============ 页面配置 ============

st.set_page_config(
    page_title="知乎舆情分析助手",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============ 自定义 CSS ============

st.markdown("""
<style>
    /* 主标题 */
    .main-title {
        text-align: center;
        padding: 1rem 0 0.5rem 0;
    }
    .main-title h1 {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .main-title p {
        color: #888;
        font-size: 1rem;
    }
    /* 情绪卡片 */
    .sentiment-card {
        border-radius: 12px;
        padding: 1.2rem;
        text-align: center;
        margin-bottom: 0.8rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        transition: transform 0.2s;
    }
    .sentiment-card:hover { transform: translateY(-2px); }
    .card-positive { background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }
    .card-negative { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
    .card-neutral  { background: linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%); }
    .card-positive, .card-negative, .card-neutral {
        color: #fff;
    }
    .card-value { font-size: 2rem; font-weight: 700; }
    .card-label { font-size: 0.9rem; opacity: 0.9; }
    /* 观点卡片 */
    .viewpoint-card {
        border-left: 4px solid;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        background: #fafafa;
        border-radius: 0 8px 8px 0;
    }
    .vp-positive { border-color: #43e97b; }
    .vp-negative { border-color: #fa709a; }
    .vp-neutral  { border-color: #a18cd1; }
    /* 关键词标签 */
    .kw-tag {
        display: inline-block;
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        margin: 0.2rem;
        font-size: 0.85rem;
    }
    /* 隐藏 Streamlit 默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ============ Session State 初始化 ============

if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "search_result" not in st.session_state:
    st.session_state.search_result = None
if "analyzing" not in st.session_state:
    st.session_state.analyzing = False

# ============ 全局实例 ============

@st.cache_resource
def get_searcher():
    return ZhihuSearcher()

@st.cache_resource
def get_analyzer():
    return SentimentAnalyzer()

@st.cache_resource
def get_wc_generator():
    return WordCloudGenerator()

@st.cache_resource
def get_formatter():
    return ReportFormatter()

# ============ 标题 ============

st.markdown("""
<div class="main-title">
    <h1>📊 知乎舆情分析助手</h1>
    <p>输入话题关键词，一键分析知乎舆论风向 | 知乎黑客松作品</p>
</div>
""", unsafe_allow_html=True)

# ============ 侧边栏 ============

with st.sidebar:
    st.header("⚙️ 分析设置")

    # 知乎 OAuth 配置
    st.subheader("🔑 知乎 API 配置")
    zhihu_app_id = st.text_input("APP_ID", value=os.getenv("ZHIHU_APP_ID", ""), type="password")
    zhihu_app_key = st.text_input("APP_KEY", value=os.getenv("ZHIHU_APP_KEY", ""), type="password")

    if zhihu_app_id and zhihu_app_key:
        st.success("✅ API 凭证已配置")
    else:
        st.info("💡 未配置 API 凭证，将使用演示数据")

    st.divider()

    # 分析参数
    st.subheader("📊 分析参数")
    limit = st.slider("搜索条数", min_value=5, max_value=50, value=20, step=5)

    data_mode = st.radio(
        "数据来源",
        ["自动（优先真实数据）", "仅演示数据"],
        index=0
    )

    use_mock_only = data_mode == "仅演示数据"

    st.divider()

    # OpenAI 配置
    st.subheader("🤖 LLM 增强（可选）")
    openai_key = st.text_input("OpenAI API Key", value=os.getenv("OPENAI_API_KEY", ""), type="password")
    openai_base = st.text_input("API Base URL", value=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))

    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
        os.environ["OPENAI_BASE_URL"] = openai_base
        st.success("✅ LLM 增强已启用")
    else:
        st.info("💡 未配置 LLM，使用本地规则分析")

    st.divider()
    st.caption("🔥 知乎黑客松参赛作品 v1.0")

# ============ 主区域：搜索 ============

col_input1, col_input2 = st.columns([5, 1])

with col_input1:
    keyword = st.text_input(
        "🔍 输入话题关键词",
        value="",
        placeholder="例如：AI大模型、新能源汽车、ChatGPT...",
        label_visibility="collapsed"
    )

with col_input2:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_btn = st.button("🚀 开始分析", type="primary", use_container_width=True)

# ============ 热门话题快捷按钮 ============

st.markdown("**🔥 热门话题**")

# 动态获取知乎热榜
ZHIHU_ACCESS_KEY = "3fc7f3480ba1b85bc04ac7be7f489a4b7a451fd2"
quick_topics = fetch_zhihu_hot()

# 失败降级：使用备份列表
if not quick_topics:
    quick_topics = [
        "樊振东加盟杜塞",
        "经济持续向好",
        "白鹿演唱会",
        "江苏税务回应偷拍",
        "下午休性价比最高",
        "小环境待太久",
        "一念江南",
        "北京男篮vs广东",
        "给阿嬷的情书",
        "汪涵槟榔",
    ]

cols = st.columns(len(quick_topics))
for i, topic in enumerate(quick_topics):
    with cols[i]:
        if st.button(topic, key=f"quick_{topic}"):
            keyword = topic
            analyze_btn = True

# ============ 分析逻辑 ============

if analyze_btn and keyword:
    st.session_state.analyzing = True
    st.session_state.analysis_result = None

    with st.spinner(f"🔍 正在分析「{keyword}」的知乎舆情..."):
        try:
            searcher = get_searcher()
            analyzer = get_analyzer()
            formatter = get_formatter()

            # 如果侧边栏填了 API 凭证，更新到环境变量
            if zhihu_app_id and zhihu_app_key:
                searcher.app_id = zhihu_app_id
                searcher.app_key = zhihu_app_key
                os.environ["ZHIHU_APP_ID"] = zhihu_app_id
                os.environ["ZHIHU_APP_KEY"] = zhihu_app_key

            # 搜索
            if use_mock_only:
                search_result = asyncio.run(searcher.search_mock(keyword))
            else:
                search_result = asyncio.run(searcher.search(keyword))
                if not search_result.answers:
                    search_result = asyncio.run(searcher.search_mock(keyword))

            st.session_state.search_result = search_result

            # 分析
            analysis_result = analyzer.analyze(search_result.answers, keyword)
            st.session_state.analysis_result = analysis_result
            st.session_state.analyzing = False

        except Exception as e:
            st.error(f"❌ 分析失败：{str(e)}")
            st.session_state.analyzing = False

# ============ 结果展示 ============

result = st.session_state.analysis_result

if result:
    st.divider()

    # --- 情绪分布概览 ---
    st.subheader("🎭 情绪分布")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="🟢 正面",
            value=f"{result.sentiment.positive_ratio*100:.1f}%",
            delta=f"{result.sentiment.positive_count} 条",
            delta_color="normal"
        )

    with col2:
        st.metric(
            label="🔴 负面",
            value=f"{result.sentiment.negative_ratio*100:.1f}%",
            delta=f"{result.sentiment.negative_count} 条",
            delta_color="inverse"
        )

    with col3:
        st.metric(
            label="🟡 中性",
            value=f"{result.sentiment.neutral_ratio*100:.1f}%",
            delta=f"{result.sentiment.neutral_count} 条"
        )

    # --- 情绪分布图（纯内联 HTML/CSS/SVG，零依赖零函数调用）---
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        pos_pct = result.sentiment.positive_ratio * 100
        neg_pct = result.sentiment.negative_ratio * 100
        neu_pct = result.sentiment.neutral_ratio * 100
        total = max(pos_pct + neg_pct + neu_pct, 0.01)
        pos_deg = pos_pct / total * 360
        neg_deg = neg_pct / total * 360
        neu_deg = neu_pct / total * 360
        C = 2 * 3.14159265 * 80
        pie_html = f"""
        <div style="text-align:center;padding:10px;">
            <strong>📊 情绪分布饼图</strong><br/><br/>
            <svg width="220" height="220" viewBox="0 0 220 220">
                <g transform="translate(110,110)">
                    <circle r="80" fill="none" stroke="#43e97b" stroke-width="35"
                            stroke-dasharray="{pos_deg/360*C} {C}" transform="rotate(-90)"/>
                    <circle r="80" fill="none" stroke="#fa709a" stroke-width="35"
                            stroke-dasharray="{neg_deg/360*C} {C}" transform="rotate({pos_deg-90})"/>
                    <circle r="80" fill="none" stroke="#a18cd1" stroke-width="35"
                            stroke-dasharray="{neu_deg/360*C} {C}" transform="rotate({pos_deg+neg_deg-90})"/>
                    <circle r="55" fill="white"/>
                    <text y="5" text-anchor="middle" font-size="13" fill="#555">{total:.0f}%</text>
                </g>
            </svg>
            <div style="margin-top:6px;font-size:0.9rem;">
                <span style="color:#43e97b;">● 正面 {pos_pct:.1f}%</span>&nbsp;&nbsp;
                <span style="color:#fa709a;">● 负面 {neg_pct:.1f}%</span>&nbsp;&nbsp;
                <span style="color:#a18cd1;">● 中性 {neu_pct:.1f}%</span>
            </div>
        </div>
        """
        st.markdown(pie_html, unsafe_allow_html=True)

    with col_chart2:
        max_cnt = max(result.sentiment.positive_count, result.sentiment.negative_count, result.sentiment.neutral_count, 1)
        bar_html = f"""
        <div style="padding:10px;">
            <strong>📊 情绪分布柱状图</strong><br/><br/>
            <div style="margin-bottom:10px;display:flex;align-items:center;">
                <span style="width:48px;color:#2e7d32;font-weight:bold;font-size:0.9rem;">正面</span>
                <div style="flex:1;background:#e8e8e8;border-radius:6px;height:26px;margin-left:8px;overflow:hidden;">
                    <div style="background:linear-gradient(90deg,#43e97b,#38f9d7);width:{result.sentiment.positive_count/max_cnt*100}%;height:100%;border-radius:6px;min-width:4px;"></div>
                </div>
                <span style="width:42px;text-align:right;margin-left:8px;font-weight:bold;color:#2e7d32;">{result.sentiment.positive_count}</span>
            </div>
            <div style="margin-bottom:10px;display:flex;align-items:center;">
                <span style="width:48px;color:#c62828;font-weight:bold;font-size:0.9rem;">负面</span>
                <div style="flex:1;background:#e8e8e8;border-radius:6px;height:26px;margin-left:8px;overflow:hidden;">
                    <div style="background:linear-gradient(90deg,#fa709a,#fee140);width:{result.sentiment.negative_count/max_cnt*100}%;height:100%;border-radius:6px;min-width:4px;"></div>
                </div>
                <span style="width:42px;text-align:right;margin-left:8px;font-weight:bold;color:#c62828;">{result.sentiment.negative_count}</span>
            </div>
            <div style="display:flex;align-items:center;">
                <span style="width:48px;color:#6a1b9a;font-weight:bold;font-size:0.9rem;">中性</span>
                <div style="flex:1;background:#e8e8e8;border-radius:6px;height:26px;margin-left:8px;overflow:hidden;">
                    <div style="background:linear-gradient(90deg,#a18cd1,#fbc2eb);width:{result.sentiment.neutral_count/max_cnt*100}%;height:100%;border-radius:6px;min-width:4px;"></div>
                </div>
                <span style="width:42px;text-align:right;margin-left:8px;font-weight:bold;color:#6a1b9a;">{result.sentiment.neutral_count}</span>
            </div>
        </div>
        """
        st.markdown(bar_html, unsafe_allow_html=True)

    # --- 舆情倾向 ---
    st.subheader("📈 舆情倾向")

    from formatter import _dominant_text
    tendency = _dominant_text(result.sentiment)

    if result.sentiment.positive_ratio > result.sentiment.negative_ratio:
        st.success(f"📊 {tendency}")
    elif result.sentiment.negative_ratio > result.sentiment.positive_ratio:
        st.warning(f"📊 {tendency}")
    else:
        st.info(f"📊 {tendency}")

    # --- 代表性观点 ---
    if result.viewpoints:
        st.subheader("💬 代表性观点")

        for i, vp in enumerate(result.viewpoints):
            stance_class = f"vp-{vp.stance}"
            stance_emoji = {"positive": "👍", "negative": "👎", "neutral": "🤔"}.get(vp.stance, "💬")
            stance_text = {"positive": "正面", "negative": "负面", "neutral": "中性"}.get(vp.stance, "中性")

            st.markdown(f"""
            <div class="viewpoint-card {stance_class}">
                <strong>{stance_emoji} 观点 {i+1}（{stance_text}）</strong>
                {f'<span style="color:#888;margin-left:8px;">【{vp.aspect}】</span>' if vp.aspect else ''}
                <br/>
                <span style="font-size:1.05rem;">{vp.summary}</span>
                <br/>
                <span style="color:#666;font-size:0.9rem;">「{vp.representative_text[:100]}{'…' if len(vp.representative_text)>100 else ''}」</span>
                {f'<br/><span style="color:#999;font-size:0.85rem;">👍 {vp.voteup_count} 赞同</span>' if vp.voteup_count else ''}
            </div>
            """, unsafe_allow_html=True)

    # --- 关键词 ---
    if result.keywords:
        st.subheader("🔑 高频关键词")

        # 标签云
        kw_html = " ".join(
            f'<span class="kw-tag">{word} ({count})</span>'
            for word, count in result.keywords[:15]
        )
        st.markdown(kw_html, unsafe_allow_html=True)

        # 关键词频率图
        if HAS_PLOTLY and HAS_PANDAS:
            kw_df = pd.DataFrame(result.keywords[:15], columns=["关键词", "频次"])
            fig_kw = px.bar(
                kw_df, x="频次", y="关键词", orientation="h",
                color="频次",
                color_continuous_scale="Viridis",
            )
            fig_kw.update_layout(
                title="关键词频率 Top 15",
                height=400,
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig_kw, use_container_width=True)
        else:
            # 用 Streamlit 原生 bar chart
            kw_data = {
                "关键词": [w for w, c in result.keywords[:15]],
                "频次": [c for w, c in result.keywords[:15]],
            }
            st.bar_chart(data=kw_data, x="关键词", y="频次", use_container_width=True)

    # --- 词云 ---
    st.subheader("☁️ 词云")
    try:
        wc_gen = get_wc_generator()
        wc_base64 = wc_gen.generate(result.keywords, output_path=None)
        if wc_base64 and len(wc_base64) > 100:
            st.markdown(
                f'<div style="text-align:center;"><img src="data:image/png;base64,{wc_base64}" width="800"/></div>',
                unsafe_allow_html=True
            )
        else:
            st.info("词云生成需要 wordcloud 库支持")
    except Exception as e:
        st.info(f"词云暂不可用：{e}")

    # --- 完整报告 ---
    st.subheader("📄 完整报告")
    formatter = get_formatter()
    report_md = formatter.format_markdown(result)

    with st.expander("📋 查看 Markdown 报告", expanded=False):
        st.markdown(report_md)

    # 下载按钮
    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        st.download_button(
            "📥 下载 Markdown 报告",
            data=report_md,
            file_name=f"舆情报告_{result.keyword}_{time.strftime('%Y%m%d')}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_dl2:
        report_json = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        st.download_button(
            "📥 下载 JSON 数据",
            data=report_json,
            file_name=f"舆情数据_{result.keyword}_{time.strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
        )

    # --- 数据来源 ---
    st.caption(f"📊 基于 {result.total_answers} 条回答的综合分析 | 分析时间：{time.strftime('%Y-%m-%d %H:%M')}")

# ============ 底部说明 ============

if not result:
    st.divider()
    st.markdown("""
    ### 🎯 使用说明

    1. **输入关键词**：在上方输入框输入你想分析的知乎话题
    2. **开始分析**：点击「开始分析」按钮，等待结果
    3. **查看报告**：情绪分布、观点提取、关键词分析一应俱全

    ### ✨ 功能特色

    | 功能 | 说明 |
    |------|------|
    | 🎭 情绪分析 | 正面/负面/中性三分类，支持 LLM 增强 |
    | 💬 观点提取 | 自动提取代表性观点，标注立场 |
    | 🔑 关键词挖掘 | N-gram + 频率分析，发现讨论焦点 |
    | ☁️ 词云可视化 | 一图看懂讨论热点 |
    | 📊 交互图表 | 饼图/柱状图/频率图 |

    > 💡 无需配置即可使用演示数据体验完整功能！
    """)



