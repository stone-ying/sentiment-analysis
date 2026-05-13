# 知乎舆情分析助手

> 🏆 知乎黑客松参赛作品

基于 Python 的知乎话题舆情分析工具，支持情感分析、关键词提取和数据可视化。

## ✨ 功能特色

- 🔍 **话题搜索** — 知乎 Open API + DuckDuckGo 多源搜索，自动降级
- 😊 **情感分析** — 本地词库规则 + LLM 双模式，支持否定词/双重否定处理
- 💬 **观点提取** — 自动提取代表性观点，标注立场和方面
- 🔑 **关键词挖掘** — N-gram + 频率分析，智能过滤碎片词
- ☁️ **词云可视化** — 自动生成关键词词云图
- 📊 **交互图表** — Plotly 饼图/柱状图/频率图
- 📄 **报告导出** — Markdown / JSON 格式一键下载
- 🌐 **Web 应用** — Streamlit 驱动，评委可直接体验

## 🚀 在线体验

访问 Streamlit Cloud 部署链接即可直接使用（无需安装）。

## 项目结构

```
sentiment_analysis/
├── streamlit_app.py          # Streamlit Web 应用入口
├── main.py                   # FastAPI 服务入口
├── cli.py                    # 命令行交互
├── analyzer.py               # 情感分析 & 关键词提取
├── searcher.py               # 知乎搜索（Open API + DuckDuckGo + Mock）
├── formatter.py              # 报告格式化
├── wordcloud_gen.py          # 词云生成
├── utils.py                  # 情感词库 & 工具函数
├── requirements.txt          # FastAPI 依赖
├── requirements.streamlit.txt # Streamlit 依赖
├── .env.example              # 环境变量模板
├── .streamlit/config.toml    # Streamlit 配置
└── output/                   # 输出目录（.gitignore）
```

## 快速开始

### 方式一：Web 应用（推荐）

```bash
pip install -r requirements.streamlit.txt
streamlit run streamlit_app.py
```

### 方式二：命令行

```bash
pip install -r requirements.txt
python cli.py AI大模型 --md
```

### 方式三：API 服务

```bash
pip install -r requirements.txt
python main.py
# 访问 http://localhost:8000/docs 查看 API 文档
```

## 配置

### 知乎 Open API（可选）

在左侧栏填入知乎开放平台的 APP_ID 和 APP_KEY，即可获取真实知乎数据。

未配置时自动使用演示数据，无需联网即可体验完整功能。

### OpenAI API（可选）

配置 OpenAI API Key 可启用 LLM 增强分析，提升情绪分类和观点提取的准确度。

## 技术栈

- **Python 3.10+**
- **Streamlit** — Web 应用框架
- **Plotly** — 交互式图表
- **FastAPI** — API 服务
- **wordcloud** — 词云生成
- **httpx** — 异步 HTTP 客户端
- **OpenAI** — LLM 增强（可选）

## License

MIT
