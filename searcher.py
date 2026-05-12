# -*- coding: utf-8 -*-
"""
知乎内容搜索模块
支持：真实搜索（知乎API + DuckDuckGo）+ Mock 降级
"""

import re
import os
import json
from typing import List, Optional
from dataclasses import dataclass, field

from utils import log

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# ============ 数据模型 ============

@dataclass
class ZhihuAnswer:
    id: str
    question: str
    author: str
    content: str
    voteup_count: int = 0
    comment_count: int = 0
    url: str = ""
    sentiment: str = ""

    def __repr__(self):
        return f"<Answer:{self.question[:20]} by {self.author} ↑{self.voteup_count}>"


@dataclass
class SearchResult:
    keyword: str
    answers: List[ZhihuAnswer] = field(default_factory=list)
    total: int = 0


# ============ 搜索器 ============

class ZhihuSearcher:
    """知乎内容搜索器，支持多种搜索源自动切换"""

    ZHIHU_API = "https://www.zhihu.com/api/v4/search_v3"
    DUCKDUCKGO = "https://html.duckduckgo.com/html/"
    BING_SEARCH = "https://cc.bingj.com/cache.aspx"

    def __init__(self, limit: int = 20):
        self.limit = limit
        self._session: Optional[httpx.AsyncClient] = None

    async def search(self, keyword: str) -> SearchResult:
        """主搜索入口：依次尝试各搜索源，成功即返回"""
        result = SearchResult(keyword=keyword)

        try:
            # 1. 知乎站内搜索
            answers = await self._search_zhihu(keyword)
            if answers:
                log.info(f"知乎搜索成功，获取 {len(answers)} 条")
                result.answers = answers[:self.limit]
                result.total = len(answers)
                return result
        except Exception as e:
            log.warning(f"知乎搜索失败: {e}")

        try:
            # 2. DuckDuckGo site:zhihu.com
            answers = await self._search_duckduckgo(keyword)
            if answers:
                log.info(f"DuckDuckGo 搜索成功，获取 {len(answers)} 条")
                result.answers = answers[:self.limit]
                result.total = len(answers)
                return result
        except Exception as e:
            log.warning(f"DuckDuckGo 搜索失败: {e}")

        # 3. 全部失败，降级到 Mock
        log.warning("所有真实搜索失败，启用 Mock 数据")
        return await self.search_mock(keyword)

    # ---- 知乎站内搜索 ----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx.AsyncClient(
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json, text/html",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                    "X-API-Version": "3.0",
                },
                timeout=15.0,
                follow_redirects=True,
            )
        return self._session

    async def _search_zhihu(self, keyword: str) -> List[ZhihuAnswer]:
        """通过必应缓存搜索知乎内容（绕过反爬）"""
        if not HAS_HTTPX:
            return []

        client = await self._get_client()

        try:
            # 直接搜索知乎问题列表
            url = f"https://www.zhihu.com/search?type=content&q={self._encode(keyword)}"
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Referer": "https://www.zhihu.com/",
            })

            if resp.status_code != 200:
                return []

            return self._parse_zhihu_html(resp.text, keyword)

        except Exception as e:
            log.debug(f"知乎搜索异常: {e}")
            return []

    def _parse_zhihu_html(self, html: str, keyword: str) -> List[ZhihuAnswer]:
        """解析知乎搜索结果 HTML"""
        answers = []

        # 提取 JSON 数据块
        json_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        match = re.search(json_pattern, html)
        if match:
            try:
                data = json.loads(match.group(1))
                items = data.get("props", {}).get("pageProps", {}).get("globalSearchData", {}).get("items", [])
                for item in items[:self.limit]:
                    q = item.get("question", {})
                    answer = item.get("answer", {})
                    if answer.get("excerpt"):
                        answers.append(ZhihuAnswer(
                            id=f"zh_{item.get('object_id', len(answers))}",
                            question=q.get("title", keyword),
                            author=answer.get("author", {}).get("name", "知乎用户"),
                            content=answer.get("excerpt", "")[:500],
                            voteup_count=answer.get("voteupCount", 0),
                            comment_count=answer.get("commentCount", 0),
                            url=item.get("url", ""),
                        ))
                return answers
            except Exception:
                pass

        # 回退：正则提取卡片
        card_pattern = r'data-za-key="[^"]*search[^"]*"(.*?)</div>\s*(?:</div>){2,}'
        cards = re.findall(card_pattern, html, re.DOTALL)
        for card in cards[:self.limit]:
            title_m = re.search(r'class="[^"]*title[^"]*"[^>]*>(.*?)</a>', card, re.DOTALL)
            content_m = re.search(r'class="[^"]*excerpt[^"]*"[^>]*>(.*?)</p>', card, re.DOTALL)
            author_m = re.search(r'class="[^"]*author[^"]*"[^>]*>(.*?)</a>', card, re.DOTALL)

            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else keyword
            content = re.sub(r'<[^>]+>', '', content_m.group(1)).strip() if content_m else ""
            author = re.sub(r'<[^>]+>', '', author_m.group(1)).strip() if author_m else "知乎用户"

            if len(content) > 20:
                answers.append(ZhihuAnswer(
                    id=f"zh_reg_{len(answers)}",
                    question=title[:80],
                    author=author or "知乎用户",
                    content=content[:500],
                ))

        return answers

    # ---- DuckDuckGo 搜索 ----

    async def _search_duckduckgo(self, keyword: str) -> List[ZhihuAnswer]:
        if not HAS_HTTPX:
            return []

        client = await self._get_client()

        try:
            resp = await client.post(
                self.DUCKDUCKGO,
                data={"q": f"site:zhihu.com {keyword}"},
            )
            if resp.status_code == 200:
                return self._parse_ddg(resp.text, keyword)
        except Exception:
            pass

        return []

    def _parse_ddg(self, html: str, keyword: str) -> List[ZhihuAnswer]:
        """解析 DuckDuckGo 搜索结果"""
        answers = []
        results = re.findall(
            r'<a class="result__a"[^>]*href="([^"]+zhihu[^"]+)"[^>]*>(.*?)</a>.*?'
            r'<a class="result__snippet"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )
        for url, title, snippet in results[:self.limit]:
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            if snippet and len(snippet) > 20:
                answers.append(ZhihuAnswer(
                    id=f"ddg_{len(answers)}",
                    question=title[:80] or keyword,
                    author="知乎用户",
                    content=snippet[:500],
                    url=url,
                ))
        return answers

    # ---- Mock 数据 ----

    async def search_mock(self, keyword: str) -> SearchResult:
        """Mock 搜索：返回丰富的测试数据"""
        mood_idx = hash(keyword) % 3  # 不同关键词不同情绪分布

        templates = {
            0: [  # 科技产品
                ("科技观察者", 1256, "整体来看，{k}是一个值得关注的领域。技术层面已有很大突破，但应用场景还需探索。核心技术已验证可行，关键是商业化落地。"),
                ("理性分析师", 832, "说实话，我对{k}持保留态度。宣传很厉害，但实际体验还有不少问题。技术成熟度不够，很多场景还是概念验证阶段。"),
                ("实践者", 543, "作为{k}的早期用户，我觉得体验还不错。核心功能很实用，效率提升明显。"),
                ("行业老兵", 2100, "我认为{k}不是泡沫，但确实存在过热问题。需要区分真正的创新和概念炒作。长期有价值，短期需降温。"),
                ("普通用户A", 321, "整体还行，不是特别惊艳但也不差。日常使用足够，偶尔有些小bug但不影响主要功能。"),
                ("乐观派", 678, "{k}代表一种趋势，从技术演进角度看是必然方向。进步很快，建议保持关注。"),
                ("怀疑论者", 1560, "很多人对{k}的期望太高了。实际用下来发现并没有宣传的那么好，很多功能还是半成品。建议理性看待。"),
                ("对比测评", 445, "我对比了几款同类产品，{k}在某些方面有优势，比如上手简单、界面友好。但深度功能还有不足。"),
                ("技术博主", 890, "作为开发者，我对{k}的技术架构比较认可。API设计合理，文档也不错。但生态还不太成熟。"),
                ("前瞻分析师", 1120, "基于目前趋势，{k}在未来1-2年会有较大发展。关键技术瓶颈正在被突破，市场需求也在增长。"),
            ],
            1: [  # 争议性话题
                ("支持者A", 2341, "{k}确实带来了巨大改变。效率提升显著，很多以前需要几天的工作现在几小时就完成了。"),
                ("反对者B", 1890, "{k}被严重夸大了。实际上问题很多，宣传与实际严重不符，谨慎对待。"),
                ("中立者C", 956, "客观说，{k}有优点也有缺点。不要全盘否定，但也不要盲目吹捧。"),
                ("深度用户", 1567, "用了三个月，我的感觉是：{k}确实有价值，但需要一定学习成本。"),
                ("怀疑者D", 1203, "很多人被营销带偏了。{k}的真实效果远不如宣传的那么好。"),
                ("行业专家", 890, "从行业角度看，{k}的趋势是明确的，但目前还在早期阶段。"),
                ("普通用户E", 567, "说实话，{k}的性价比一般。值不值得买取决于具体需求。"),
                ("从业者F", 734, "我在这个行业工作，{k}确实在改变工作方式。短期内会有挑战，长期看好。"),
                ("学生G", 423, "作为学生，我觉得{k}很有帮助。但价格对学生不太友好。"),
                ("媒体人H", 1121, "采访了很多相关人士，对{k}的评价两极分化。真相可能介于两者之间。"),
            ],
            2: [  # 新兴话题
                ("早期采用者", 678, "{k}是个很有前景的方向。尝鲜体验超出预期，值得关注。目前虽然还在早期，但技术路线清晰。"),
                ("技术宅", 890, "研究了一下{k}的技术原理，确实有创新。但目前生态还不完善，文档也比较少，学习曲线有点陡。"),
                ("普通用户", 234, "试用了{k}，感觉还不错。虽然还有很多改进空间，但方向是对的，用户体验在持续改善。"),
                ("观望者", 456, "对{k}保持观望态度。等市场更成熟一些再决定是否投入。目前不确定性还比较多。"),
                ("从业者", 1234, "{k}正在快速发展。我们团队已经在布局相关产品和解决方案，预计下半年会有实际产出。"),
                ("行业分析师", 2100, "从行业趋势来看，{k}处于技术成熟度曲线的上升期。虽然短期有波动，但3-5年维度看非常有潜力。"),
                ("尝鲜用户", 345, "刚入手{k}一周，上手比想象中简单。核心功能已经比较完善，一些高级功能还在打磨中。总体满意。"),
                ("审慎者", 876, "我对{k}持谨慎乐观态度。概念很好，但要真正落地还有不少技术瓶颈需要突破。建议理性看待。"),
                ("投资人视角", 1567, "从投资角度看，{k}赛道正在升温。虽然估值有些高，但头部项目的技术和团队都不错。关注后续商业化进展。"),
                ("产品经理", 543, "作为产品经理，我认为{k}解决了真实的用户痛点。但目前的市场教育成本偏高，需要更多标杆案例来推动普及。"),
            ],
        }

        answers = []
        templates_list = templates.get(mood_idx, templates[0])
        for author, votes, template in templates_list:
            answers.append(ZhihuAnswer(
                id=f"mock_{len(answers)}",
                question=f"关于{keyword}的讨论",
                author=author,
                content=template.format(k=keyword),
                voteup_count=votes,
                comment_count=votes // 10,
            ))

        return SearchResult(keyword=keyword, answers=answers, total=len(answers))

    @staticmethod
    def _encode(s: str) -> str:
        import urllib.parse
        return urllib.parse.quote(s)