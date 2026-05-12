# 知乎舆情分析助手

基于 Python 的知乎话题舆情分析工具，支持情感分析、关键词提取和数据可视化。

## 功能

- 🔍 **话题搜索** — 搜索知乎问答，获取高赞回答
- 😊 **情感分析** — 基于词库的中文情感评分（正面/负面/中性）
- 🔑 **关键词提取** — N-gram 分词 + TF-IDF 关键词挖掘
- ☁️ **词云生成** — 自动生成关键词词云图
- 📊 **报告输出** — JSON 格式结构化分析报告

## 项目结构

`sentiment_analysis/
├── main.py           # 主入口
├── cli.py            # 命令行交互
├── analyzer.py       # 情感分析 & 关键词提取
├── searcher.py       # 知乎搜索（API + Mock）
├── formatter.py      # 报告格式化
├── wordcloud_gen.py  # 词云生成
├── utils.py          # 情感词库 & 工具函数
├── requirements.txt  # 依赖
├── .env.example      # 环境变量模板
└── output/           # 输出目录（.gitignore）
``

## 快速开始

1. 安装依赖：
   ``bash
   pip install -r requirements.txt
   ``

2. 配置环境变量（可选，用于真实 API）：
   ``bash
   cp .env.example .env
   # 编辑 .env 填入 API Key
   ``

3. 运行分析：
   ``bash
   python main.py
   ``

> 无 API Key 时自动使用 Mock 模式，无需联网即可体验完整功能。

## 技术栈

- Python 3.10+
- jieba（中文分词）
- wordcloud（词云生成）
- requests（API 调用）

## License

MIT
