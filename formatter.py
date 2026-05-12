# -*- coding: utf-8 -*-
"""
报告格式化模块
将分析结果格式化为可读报告（文本/Markdown/JSON/Hook）
"""

from datetime import datetime
from typing import List
from analyzer import AnalysisResult, SentimentResult, Viewpoint


# ============ 进度条渲染 ============

def _bar(ratio: float, width: int = 20, pos_char: str = "█", neg_char: str = "▓", neu_char: str = "░") -> str:
    filled = max(1, int(ratio * width))
    return pos_char * filled + neu_char * (width - filled)


# ============ 格式化器 ============

class ReportFormatter:
    """多格式报告格式化器"""

    # ---- 纯文本报告 ----

    @staticmethod
    def format_text(result: AnalysisResult) -> str:
        s = result.sentiment
        lines = []

        lines.append(f"📊 舆情分析报告：{result.keyword}")
        lines.append("=" * 52)
        lines.append("")

        # 概览
        lines.append("📋 概览")
        lines.append("-" * 30)
        lines.append(f"  分析话题   ：{result.keyword}")
        lines.append(f"  样本数量   ：{result.total_answers} 条回答")
        lines.append(f"  分析时间   ：{_now()}")
        lines.append("")

        # 情绪分布（带进度条）
        lines.append("🎭 情绪分布")
        lines.append("-" * 30)
        total = s.positive_count + s.negative_count + s.neutral_count
        if total > 0:
            lines.append(
                f"  🟢 正面  {s.positive_ratio*100:+6.1f}% "
                f"| {_bar(s.positive_ratio, 12)} "
                f"({s.positive_count}条)"
            )
            lines.append(
                f"  🔴 负面  {s.negative_ratio*100:+6.1f}% "
                f"| {_bar(s.negative_ratio, 12)} "
                f"({s.negative_count}条)"
            )
            lines.append(
                f"  🟡 中性  {s.neutral_ratio*100:+6.1f}% "
                f"| {_bar(s.neutral_ratio, 12)} "
                f"({s.neutral_count}条)"
            )
        lines.append("")

        # 舆情倾向一句话
        lines.append("📈 舆情倾向")
        lines.append("-" * 30)
        lines.append(f"  {_dominant_text(s)}")
        lines.append("")

        # 代表性观点
        if result.viewpoints:
            lines.append("💬 代表性观点")
            lines.append("-" * 30)
            for i, vp in enumerate(result.viewpoints, 1):
                emoji = _stance_emoji(vp.stance)
                stance_txt = _stance_text(vp.stance)
                lines.append(
                    f"  {emoji} 观点{i}（{stance_txt}）"
                    f"【{vp.aspect}】"
                )
                lines.append(f"     {vp.summary}")
                lines.append(
                    f"     📄「{vp.representative_text[:70]}"
                    f"{'…' if len(vp.representative_text) > 70 else ''}」"
                )
                if vp.voteup_count:
                    lines.append(f"     👍 {vp.voteup_count} 赞同")
                lines.append("")

        # 关键词（带频率条）
        if result.keywords:
            lines.append("🔑 高频关键词")
            lines.append("-" * 30)
            max_cnt = max(c for _, c in result.keywords) if result.keywords else 1
            for word, cnt in result.keywords[:10]:
                bar_len = max(1, int(cnt / max_cnt * 15))
                bar = "█" * bar_len
                lines.append(f"  {word:<12s}  {bar}  {cnt}")
            lines.append("")

        # 总结
        lines.append("📝 总结")
        lines.append("-" * 30)
        lines.append(f"  {_summary_text(result)}")
        lines.append("")
        lines.append("=" * 52)
        lines.append(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 生成")

        return "\n".join(lines)

    # ---- JSON 结构 ----

    @staticmethod
    def format_json(result: AnalysisResult) -> dict:
        return result.to_dict()

    # ---- Markdown 报告 ----

    @staticmethod
    def format_markdown(result: AnalysisResult) -> str:
        s = result.sentiment
        lines = []

        lines.append(f"# 📊 舆情分析报告：`{result.keyword}`")
        lines.append("")
        lines.append(f"> **分析时间**：{_now()}  |  **样本量**：{result.total_answers} 条")
        lines.append("")

        # 情绪分布
        lines.append("## 🎭 情绪分布")
        lines.append("")
        lines.append("| 情绪 | 比例 | 数量 | 趋势 |")
        lines.append("|------|------|------|------|")
        lines.append(
            f"| 🟢 正面 | {s.positive_ratio*100:.1f}% | {s.positive_count} | "
            f"{_bar_md(s.positive_ratio)} |"
        )
        lines.append(
            f"| 🔴 负面 | {s.negative_ratio*100:.1f}% | {s.negative_count} | "
            f"{_bar_md(s.negative_ratio)} |"
        )
        lines.append(
            f"| 🟡 中性 | {s.neutral_ratio*100:.1f}% | {s.neutral_count} | "
            f"{_bar_md(s.neutral_ratio)} |"
        )
        lines.append("")

        # 舆情倾向卡片
        lines.append("## 📈 舆情倾向")
        lines.append("")
        lines.append(f"> {_dominant_text(s)}")
        lines.append("")

        # 代表性观点
        if result.viewpoints:
            lines.append("## 💬 代表性观点")
            lines.append("")
            for i, vp in enumerate(result.viewpoints, 1):
                emoji = _stance_emoji(vp.stance)
                stance_txt = _stance_text(vp.stance)
                lines.append(f"### {emoji} 观点 {i}（{stance_txt}）")
                if vp.aspect:
                    lines.append(f"> **方面**：{vp.aspect}")
                lines.append(f"> **{vp.summary}**")
                lines.append("")
                lines.append(f"> 📄 {vp.representative_text[:100]}")
                if vp.voteup_count:
                    lines.append(f"> 👍 {vp.voteup_count} 次赞同")
                lines.append("")

        # 关键词
        if result.keywords:
            lines.append("## 🔑 高频关键词")
            lines.append("")
            lines.append("| 关键词 | 频次 | 趋势 |")
            lines.append("|--------|------|------|")
            max_cnt = max(c for _, c in result.keywords) if result.keywords else 1
            for word, cnt in result.keywords[:10]:
                lines.append(
                    f"| {word} | {cnt} | "
                    f"{_bar_md(cnt / max_cnt)} |"
                )
            lines.append("")

        # 总结
        lines.append("## 📝 总结")
        lines.append("")
        lines.append(_summary_text(result))

        return "\n".join(lines)

    # ---- A2A Hook 格式 ----

    @staticmethod
    def format_a2a_hook(result: AnalysisResult, style: str = "brief") -> str:
        """专为 A2A / Agent 间传递设计的简洁 Hook 文本"""
        s = result.sentiment
        lines = []

        if style == "brief":
            lines.append(f"【{result.keyword} 舆情分析】")
            lines.append(f"📊 样本 {result.total_answers} 条 | "
                        f"🟢 {s.positive_ratio*100:.0f}% "
                        f"🔴 {s.negative_ratio*100:.0f}% "
                        f"🟡 {s.neutral_ratio*100:.0f}%")
            lines.append(f"📈 {_dominant_text(s)}")
            if result.viewpoints:
                top = result.viewpoints[0]
                lines.append(f"💬 {top.summary}")
            lines.append(f"🔑 {result.keywords[0][0] if result.keywords else 'N/A'}")

        elif style == "full":
            lines.append(f"舆情报告：{result.keyword}")
            lines.append(f"正面 {s.positive_count} | 负面 {s.negative_count} | 中性 {s.neutral_count}")
            for vp in result.viewpoints[:3]:
                lines.append(f"- [{_stance_text(vp.stance)}] {vp.summary}")
            lines.append(f"关键词：{', '.join(w for w, _ in result.keywords[:5])}")

        return "\n".join(lines)


# ============ 辅助函数 ============

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _dominant_text(s: SentimentResult) -> str:
    pos = s.positive_ratio
    neg = s.negative_ratio
    neu = s.neutral_ratio

    if neu > 0.6:
        return f"讨论整体中性（{neu*100:.0f}%），观点相对理性客观"
    elif pos > neg * 1.5:
        return f"舆情偏正面（{pos*100:.0f}%），支持声音占主导"
    elif neg > pos * 1.5:
        return f"舆情偏负面（{neg*100:.0f}%），质疑和批评较多"
    elif abs(pos - neg) < 0.15:
        return f"舆论分化明显，正负各半（正面{pos*100:.0f}% vs 负面{neg*100:.0f}%）"
    elif pos > neg:
        return f"整体倾向正面（正面{pos*100:.0f}% vs 负面{neg*100:.0f}%）"
    else:
        return f"整体倾向负面（负面{neg*100:.0f}% vs 正面{pos*100:.0f}%）"


def _bar_md(ratio: float, width: int = 10) -> str:
    filled = max(1, int(ratio * width))
    return "█" * filled + "░" * (width - filled)


_STANCE_MAP = {
    "positive": ("👍", "正面"),
    "negative": ("👎", "负面"),
    "neutral": ("🤔", "中性"),
}


def _stance_emoji(s: str) -> str:
    return _STANCE_MAP.get(s, ("💬", "中性"))[0]


def _stance_text(s: str) -> str:
    return _STANCE_MAP.get(s, ("💬", "中性"))[1]


def _summary_text(result: AnalysisResult) -> str:
    s = result.sentiment
    kw = ", ".join([w for w, _ in result.keywords[:5]])
    return (
        f"关于「{result.keyword}」的讨论{_dominant_text(s)}。"
        f"关键词包括：{kw}。"
        f"基于{result.total_answers}条回答的综合分析。"
    )