# -*- coding: utf-8 -*-
"""
舆情分析助手 — 命令行工具
用法: python cli.py [keyword] [options]

选项:
  --real      使用真实搜索（默认使用模拟数据）
  --json      输出 JSON 格式
  --md        输出 Markdown 格式
  --wordcloud 生成词云图片
"""

import asyncio
import sys
import os
import io

# Windows 终端 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(__file__))

from searcher import ZhihuSearcher
from analyzer import SentimentAnalyzer
from wordcloud_gen import WordCloudGenerator
from formatter import ReportFormatter
from utils import log


async def main():
    args = sys.argv[1:]
    use_mock = "--real" not in args
    output_json = "--json" in args
    output_md = "--md" in args
    gen_wordcloud = "--wordcloud" in args

    # 解析关键词（去除选项）
    keyword = " ".join(a for a in args if not a.startswith("--")) or "AI编程"

    searcher = ZhihuSearcher()
    analyzer = SentimentAnalyzer()
    formatter = ReportFormatter()

    print(f"\n🔍 正在分析话题：「{keyword}」...\n")

    # 搜索
    if use_mock:
        print("📝 使用模拟数据（加 --real 使用真实搜索）\n")
        search_result = await searcher.search_mock(keyword)
    else:
        search_result = await searcher.search(keyword)
        if not search_result.answers:
            print("⚠️ 真实搜索失败，切换到模拟数据\n")
            search_result = await searcher.search_mock(keyword)

    print(f"📊 获取到 {search_result.total} 条回答\n")

    # 分析
    print("🧠 正在分析情绪...")
    analysis_result = analyzer.analyze(search_result.answers, keyword)

    # 输出
    if output_json:
        import json
        print(json.dumps(analysis_result.to_dict(), ensure_ascii=False, indent=2))
    elif output_md:
        print(formatter.format_markdown(analysis_result))
    else:
        print(formatter.format_text(analysis_result))

    # 词云
    if gen_wordcloud:
        print("\n🎨 正在生成词云和图表...")
        wc = WordCloudGenerator()
        output_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(output_dir, exist_ok=True)

        wc_path = os.path.join(output_dir, f"wordcloud_{keyword}.png")
        wc.generate(analysis_result.keywords, wc_path)
        print(f"  ✅ 词云: {wc_path}")

        chart_path = os.path.join(output_dir, f"sentiment_{keyword}.png")
        wc.generate_sentiment_chart(analysis_result.sentiment, chart_path)
        print(f"  ✅ 情绪饼图: {chart_path}")

    # 保存报告
    output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    report_path = os.path.join(output_dir, f"report_{keyword}.md")
    md = formatter.format_markdown(analysis_result)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"\n📄 报告已保存: {report_path}\n")


if __name__ == "__main__":
    asyncio.run(main())
