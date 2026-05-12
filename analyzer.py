# -*- coding: utf-8 -*-
"""
情绪分析 + 观点提取模块
使用 LLM 对知乎回答进行情绪分析和观点提取
支持双模式：无 API Key 时使用本地规则分析
"""

import os
import json
import re
from collections import Counter
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

from searcher import ZhihuAnswer
from utils import (
    log, STOPWORDS, POSITIVE_WORDS, NEGATIVE_WORDS,
    NEGATION_WORDS, NOT_NEGATION_COMPOUNDS, PRONOUNS, PUNCTUATION,
)

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


# ============ 数据模型 ============

@dataclass
class SentimentResult:
    """情绪分析结果"""
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    positive_ratio: float = 0.0
    negative_ratio: float = 0.0
    neutral_ratio: float = 0.0

    @property
    def dominant(self) -> str:
        """主导情绪"""
        counts = [("positive", self.positive_count),
                  ("negative", self.negative_count),
                  ("neutral", self.neutral_count)]
        return max(counts, key=lambda x: x[1])[0]

    @property
    def scores(self) -> Dict[str, float]:
        return {
            "positive": self.positive_ratio,
            "negative": self.negative_ratio,
            "neutral": self.neutral_ratio,
        }


@dataclass
class Viewpoint:
    """代表性观点"""
    stance: str          # positive / negative / neutral
    summary: str         # 观点摘要
    representative_text: str  # 原文摘录
    voteup_count: int = 0
    aspect: str = ""     # 观点涉及的方面


@dataclass
class AnalysisResult:
    """完整分析结果"""
    keyword: str
    total_answers: int
    sentiment: SentimentResult
    viewpoints: List[Viewpoint] = field(default_factory=list)
    keywords: List[Tuple[str, int]] = field(default_factory=list)
    _raw_answers: List[ZhihuAnswer] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "total_answers": self.total_answers,
            "sentiment": {
                "positive": {"count": self.sentiment.positive_count, "ratio": self.sentiment.positive_ratio},
                "negative": {"count": self.sentiment.negative_count, "ratio": self.sentiment.negative_ratio},
                "neutral":  {"count": self.sentiment.neutral_count,  "ratio": self.sentiment.neutral_ratio},
            },
            "viewpoints": [
                {"stance": v.stance, "summary": v.summary,
                 "representative_text": v.representative_text,
                 "voteup_count": v.voteup_count, "aspect": v.aspect}
                for v in self.viewpoints
            ],
            "keywords": [{"word": w, "count": c} for w, c in self.keywords],
        }


# ============ 情绪分析器 ============

class SentimentAnalyzer:
    """知乎回答情绪分析器"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model
        self.use_llm = bool(self.api_key) and HAS_OPENAI

        if self.use_llm:
            try:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                log.info(f"LLM 模式启动，使用模型: {self.model}")
            except Exception as e:
                log.warning(f"OpenAI 客户端初始化失败: {e}，降级到本地模式")
                self.use_llm = False
                self.client = None
        else:
            log.info("本地规则模式启动（无 API Key）")
            self.client = None

    def analyze(self, answers: List[ZhihuAnswer], keyword: str) -> AnalysisResult:
        """
        对回答列表进行情绪分析
        """
        if not answers:
            return AnalysisResult(
                keyword=keyword,
                total_answers=0,
                sentiment=SentimentResult(),
            )

        log.info(f"开始分析 {len(answers)} 条回答，关键字: {keyword}")

        # 第一步：批量情绪分类
        sentiments = self._classify_sentiments(answers, keyword)

        # 第二步：提取代表性观点
        viewpoints = self._extract_viewpoints(answers, keyword)

        # 第三步：提取关键词
        keywords = self._extract_keywords(answers, keyword)

        # 统计情绪分布
        sentiment_result = self._compute_sentiment_stats(sentiments)

        # 更新回答的情绪标签
        for answer, sentiment in zip(answers, sentiments):
            answer.sentiment = sentiment

        log.info(
            f"分析完成 | 正面:{sentiment_result.positive_count} "
            f"负面:{sentiment_result.negative_count} "
            f"中性:{sentiment_result.neutral_count}"
        )

        return AnalysisResult(
            keyword=keyword,
            total_answers=len(answers),
            sentiment=sentiment_result,
            viewpoints=viewpoints,
            keywords=keywords,
            _raw_answers=answers,
        )

    # ---- LLM 模式 ----

    def _classify_sentiments(self, answers: List[ZhihuAnswer], keyword: str) -> List[str]:
        """批量情绪分类（双模式路由）"""
        if not self.use_llm:
            return self._classify_local(answers, keyword)
        return self._classify_via_llm(answers, keyword)

    def _classify_via_llm(self, answers: List[ZhihuAnswer], keyword: str) -> List[str]:
        """通过 LLM 进行情绪分类"""
        texts = [f"[{i+1}] {a.author}: {a.content[:200]}" for i, a in enumerate(answers)]

        prompt = (
            f'分析以下关于"{keyword}"的知乎回答的情绪倾向。'
            f"对每条回答，只输出一个标签：positive（正面）、negative（负面）或 neutral（中性）。\n\n"
            + "\n".join(texts) +
            "\n\n请按以下格式输出，每行一条，不要其他内容：\n1: positive\n2: negative\n3: neutral\n..."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": "你是一个舆情分析专家。只输出分类结果，不要解释。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=500,
            )

            result_text = response.choices[0].message.content.strip()
            sentiments = []
            for line in result_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    sentiment = line.split(":")[-1].strip().lower()
                    if sentiment in ("positive", "negative", "neutral"):
                        sentiments.append(sentiment)
                    else:
                        sentiments.append("neutral")
                elif line in ("positive", "negative", "neutral"):
                    sentiments.append(line)

            while len(sentiments) < len(answers):
                sentiments.append("neutral")
            return sentiments[:len(answers)]

        except Exception as e:
            log.error(f"LLM 情绪分类失败: {e}，降级到本地规则")
            return self._classify_local(answers, keyword)

    # ---- 本地规则模式 ----

    def _classify_local(self, answers: List[ZhihuAnswer], keyword: str) -> List[str]:
        """
        本地规则情绪分类
        特点：
        1. 加权情感词（不只是计数）
        2. 否定词检测（如"不推荐"、"没问题"）
        3. 双重否定处理
        4. 上下文感知（距离越近权重越高）
        """
        sentiments = []
        for answer in answers:
            score = self._score_sentiment(answer.content)
            if score > 1.0:
                sentiments.append("positive")
            elif score < -1.0:
                sentiments.append("negative")
            else:
                sentiments.append("neutral")
        return sentiments

    def _score_sentiment(self, text: str) -> float:
        """
        计算文本的情感得分
        正数 = 正面，负数 = 负面，绝对值越大情绪越强
        """
        score = 0.0

        # 扫描情感词和否定词
        for neg_word in NEGATION_WORDS:
            idx = text.find(neg_word)
            while idx != -1:
                # 找到否定词后，在其作用域内查找情感词
                scope_end = min(idx + 5, len(text))
                scope = text[idx:scope_end]

                # 检测否定词后紧跟的情感词
                for pos_word, weight in POSITIVE_WORDS.items():
                    if pos_word in scope:
                        # 跳过含有"不"的正面复合词（如"不错"≠负面，"不赖"≠负面）
                        if pos_word in NOT_NEGATION_COMPOUNDS:
                            continue
                        score -= weight * 0.9
                        break
                for neg_word2, weight in NEGATIVE_WORDS.items():
                    if neg_word2 in scope:
                        # 防止双重反转：如"不推荐"中的"不"已翻转"推荐"，
                        # 不应再把"不推荐"（含"不"的完整贬义词）反转为正面
                        if neg_word in neg_word2 or neg_word2 in NOT_NEGATION_COMPOUNDS:
                            continue
                        score += weight * 0.9
                        break

                idx = text.find(neg_word, idx + 1)

        # 扫描正向情感词
        for word, weight in POSITIVE_WORDS.items():
            count = text.count(word)
            if count > 0:
                # 计算最小距离用于衰减
                score += weight * count

        # 扫描负向情感词
        for word, weight in NEGATIVE_WORDS.items():
            count = text.count(word)
            if count > 0:
                score -= weight * count

        # 检测感叹号强化（"很棒！" 强于 "很棒"）
        exclamations = text.count("！") + text.count("!")
        if exclamations > 0:
            score *= (1 + exclamations * 0.1)

        return score

    # ---- 观点提取 ----

    def _extract_viewpoints(self, answers: List[ZhihuAnswer], keyword: str) -> List[Viewpoint]:
        """提取代表性观点"""
        if not self.use_llm:
            return self._extract_viewpoints_local(answers, keyword)
        return self._extract_viewpoints_via_llm(answers, keyword)

    def _extract_viewpoints_via_llm(self, answers: List[ZhihuAnswer], keyword: str) -> List[Viewpoint]:
        sorted_answers = sorted(answers, key=lambda a: a.voteup_count, reverse=True)[:5]
        texts = [f"[{i+1}] {a.author}(赞{a.voteup_count}): {a.content[:300]}"
                 for i, a in enumerate(sorted_answers)]

        prompt = (
            f'从以下关于"{keyword}"的高赞知乎回答中，提取3-5个代表性观点。\n'
            f"每个观点提供: stance(positive/negative/neutral), summary(30字内), source_index。\n\n"
            + "\n".join(texts) +
            "\n\nJSON数组格式: [{\"stance\": \"...\", \"summary\": \"...\", \"source_index\": 1}, ...]"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": "你是舆情分析专家。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=800,
            )

            result_text = response.choices[0].message.content.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            viewpoints_data = json.loads(result_text)
            viewpoints = []
            for vp in viewpoints_data:
                idx = vp.get("source_index", 1) - 1
                if 0 <= idx < len(sorted_answers):
                    source = sorted_answers[idx]
                    viewpoints.append(Viewpoint(
                        stance=vp.get("stance", "neutral"),
                        summary=vp.get("summary", ""),
                        representative_text=source.content[:150],
                        voteup_count=source.voteup_count,
                        aspect=vp.get("aspect", ""),
                    ))
            return viewpoints

        except Exception as e:
            log.error(f"LLM 观点提取失败: {e}，降级到本地模式")
            return self._extract_viewpoints_local(answers, keyword)

    def _extract_viewpoints_local(self, answers: List[ZhihuAnswer], keyword: str) -> List[Viewpoint]:
        """本地模式：按点赞和情感多样性提取代表性观点"""
        sorted_answers = sorted(answers, key=lambda a: a.voteup_count, reverse=True)
        sentiments = self._classify_local(sorted_answers, keyword)

        # 确保多样性：正/负/中各取代表
        by_sentiment: Dict[str, List[tuple]] = {"positive": [], "negative": [], "neutral": []}
        for a, s in zip(sorted_answers, sentiments):
            by_sentiment[s].append((a, s))

        viewpoints = []
        seen_content = set()

        for stance in ["negative", "positive", "neutral"]:
            candidates = by_sentiment.get(stance, [])
            for answer, s in candidates:
                if answer.content[:50] in seen_content:
                    continue
                seen_content.add(answer.content[:50])

                score = self._score_sentiment(answer.content)
                summary = self._summarize_local(answer.content, score)
                viewpoints.append(Viewpoint(
                    stance=s,
                    summary=summary,
                    representative_text=answer.content[:150],
                    voteup_count=answer.voteup_count,
                    aspect=self._extract_aspect_local(answer.content, keyword),
                ))
                if len(viewpoints) >= 5:
                    break
            if len(viewpoints) >= 5:
                break

        # 按点赞排序
        viewpoints.sort(key=lambda v: v.voteup_count, reverse=True)
        return viewpoints[:5]

    def _summarize_local(self, text: str, score: float) -> str:
        """本地摘要：从文本中提取最有信息量的句子"""
        sentences = re.split(r'[。！？\n]', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
        if not sentences:
            return text[:50] + "..." if len(text) > 50 else text

        # 选情感最强的句子作为摘要
        best = max(sentences, key=lambda s: abs(self._score_sentiment(s)) if s.strip() else 0)
        return best[:50] + "..." if len(best) > 50 else best

    def _extract_aspect_local(self, text: str, keyword: str) -> str:
        """提取观点涉及的方面"""
        text_lower = text.lower()
        aspects = []
        aspect_map = {
            "性能": ["性能", "速度", "卡顿", "流畅", "快", "慢"],
            "价格": ["价格", "性价比", "贵", "便宜", "钱", "成本"],
            "功能": ["功能", "特性", "能力", "支持"],
            "体验": ["体验", "界面", "设计", "易用", "上手"],
            "质量": ["质量", "稳定", "bug", "崩溃"],
            "生态": ["生态", "插件", "第三方", "社区"],
        }
        for aspect, keywords in aspect_map.items():
            if any(k in text_lower for k in keywords):
                aspects.append(aspect)
        return "、".join(aspects[:2]) if aspects else "综合"

    # ---- 关键词提取 ----

    def _extract_keywords(self, answers: List[ZhihuAnswer], keyword: str) -> List[Tuple[str, int]]:
        """提取关键词"""
        if not self.use_llm:
            return self._extract_keywords_local(answers, keyword)
        return self._extract_keywords_via_llm(answers, keyword)

    def _extract_keywords_via_llm(self, answers: List[ZhihuAnswer], keyword: str) -> List[Tuple[str, int]]:
        all_text = " ".join([a.content for a in answers])
        prompt = (
            f'从以下关于"{keyword}"的讨论文本中，提取10个最关键的高频词汇'
            f'（排除"{keyword}"本身和常见停用词）。\n\n'
            f"文本：\n{all_text[:2000]}\n\n"
            f"JSON数组：[{{\"word\": \"词汇\", \"count\": 频次}}, ...]"
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是文本分析专家。只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
            )
            result_text = response.choices[0].message.content.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            keywords_data = json.loads(result_text)
            return [(item["word"], item["count"]) for item in keywords_data]
        except Exception as e:
            log.error(f"LLM 关键词提取失败: {e}，降级到本地模式")
            return self._extract_keywords_local(answers, keyword)

    def _extract_keywords_local(self, answers: List[ZhihuAnswer], keyword: str) -> List[Tuple[str, int]]:
        """
        单次滑动窗口提取 ngram 关键词（已修复中文/英文混合碎片 bug）
        过滤 'I编'、'AI编'（英文缩写中间被截断）等无意义碎片。
        """
        all_text = "".join([a.content for a in answers])
        n = len(all_text)

        counter = Counter()

        i = 0
        while i < n:
            # 找下一个标点作为词边界
            j = i
            while j < n and all_text[j] not in PUNCTUATION:
                j += 1

            # 对整段做滑动窗口提取所有 ngram
            segment = all_text[i:j]
            seg_len = j - i

            for pos in range(seg_len - 1):
                w2 = segment[pos:pos+2]
                if self._is_valid_ngram(w2):
                    counter[w2] += 1

            for pos in range(seg_len - 2):
                w3 = segment[pos:pos+3]
                if self._is_valid_ngram(w3):
                    counter[w3] += 1

            for pos in range(seg_len - 3):
                w4 = segment[pos:pos+4]
                if self._is_valid_ngram(w4):
                    counter[w4] += 1

            i = j + 1  # 跳过标点

        # 去重重叠词：保留更长的有意义词（AI编程 > AI编 > I编程）
        result = []
        seen_words = set()
        for word, cnt in counter.most_common(60):
            if cnt < 2:
                continue
            if word in seen_words:
                continue
            # 跳过已收录词的反向情况（但保留有独立意义的短词）
            dominated = False
            for w in list(seen_words):
                if word in w or w in word:
                    # 如果当前词比已有词短且已有词包含它，跳过
                    if len(word) <= len(w) and w.startswith(word):
                        dominated = True
                        break
                    # 如果当前词比已有词长，已有词是它的子串，跳过（更长的词更准确）
                    if len(word) > len(w) and word.startswith(w):
                        dominated = True
                        break
            if dominated:
                continue
            result.append((word, cnt))
            seen_words.add(word)
            if len(result) >= 10:
                break

        return result

    def _is_valid_ngram(self, ngram: str) -> bool:
        """
        检查 ngram 是否有意义，拒绝英文缩写被中文切断的碎片（如 'I编'、'AI编'）
        """
        if ngram in STOPWORDS:
            return False
        if any(c in STOPWORDS for c in ngram):
            return False

        # 全部ASCII → 可能是英文词，只要长度合理就接受
        if ngram.isascii() and ngram.isalpha():
            return 2 <= len(ngram) <= 20

        # 全部CJK → 接受
        if all('\u4e00' <= c <= '\u9fff' for c in ngram):
            return True

        # 混合 CJK + ASCII：检查英文是否被正确保留
        # 规则：单个ASCII字母紧邻CJK → 碎片（如 'I编'、'AI编' 中的 'I编'）
        # 规则：ASCII缩写（2+字母）紧邻CJK → 正常（如 'AI编程' 中的 'AI编'，'AI' 是缩写）
        for pos in range(len(ngram) - 1):
            c1, c2 = ngram[pos], ngram[pos + 1]
            c1_alpha = c1.isascii() and c1.isalpha()
            c2_alpha = c2.isascii() and c2.isalpha()
            c1_cjk = '\u4e00' <= c1 <= '\u9fff'
            c2_cjk = '\u4e00' <= c2 <= '\u9fff'

            # 单字母紧邻CJK（无其他字母包裹）→ 碎片
            if c1_alpha and c2_cjk:
                # 检查 c1 左边是否也是字母（形成缩写的一部分）
                if pos == 0 or not (ngram[pos - 1].isascii() and ngram[pos - 1].isalpha()):
                    return False
            if c1_cjk and c2_alpha:
                # 检查 c2 右边是否也是字母
                if pos + 2 >= len(ngram) or not (ngram[pos + 2].isascii() and ngram[pos + 2].isalpha()):
                    return False

        return True

    # ---- 统计计算 ----

    def _compute_sentiment_stats(self, sentiments: List[str]) -> SentimentResult:
        total = len(sentiments)
        if total == 0:
            return SentimentResult()

        positive = sentiments.count("positive")
        negative = sentiments.count("negative")
        neutral = sentiments.count("neutral")

        return SentimentResult(
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            positive_ratio=round(positive / total, 3),
            negative_ratio=round(negative / total, 3),
            neutral_ratio=round(neutral / total, 3),
        )
