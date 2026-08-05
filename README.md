# 📈 AI 投研助手 (AI Investment Copilot)

一个面向个人投资者与金融学习者的 **AI 投研助手**，集成大语言模型（LLM）与检索增强生成（RAG），实现个股行情解读、财报/新闻速读、研报智能问答三大功能。

> 本项目从一个 Coze 无代码理财科普 Agent 升级而来，目标是用代码完整实现一套「数据 → LLM 分析 → RAG 问答」的 AI 应用闭环。

---

## ✨ 功能

| 模块 | 说明 |
|---|---|
| 📊 **个股行情分析** | 输入 A 股代码，自动拉取行情、计算 MA/RSI 技术指标，并由 LLM 生成专业解读 |
| 📰 **财报/新闻速读** | 粘贴财报或新闻文本，AI 提炼关键要点、判断情绪倾向、提示风险 |
| 📚 **研报问答 (RAG)** | 上传研报 PDF，基于向量检索 + LLM 对文档内容进行精准问答 |

## 🛠 技术栈

- **前端 / 应用层**：Streamlit
- **大模型**：OpenAI 兼容接口（可对接 OpenAI / DeepSeek / 通义 / 智谱等）
- **RAG**：自实现向量检索（embedding + 余弦相似度），无重型依赖，便于理解原理
- **金融数据**：akshare（免费）
- **数据处理**：pandas / numpy

## 🚀 快速开始

```bash
# 1. 使用 Python 3.12 安装依赖
uv sync --all-groups

# 2. 配置 API key（复制示例文件后填入自己的 key）
cp .env.example .env
# 然后编辑 .env

# 3. 启动
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。

## 评分数据质量门

`scoring.py` 提供两种评分入口：现有 Streamlit 和 LangGraph 路径在迁移期间继续
调用 `score_stock()`，其按旧有的缺失指标归一化语义运行；新的 API 调用方必须使用
`evaluate_score()`。

`evaluate_score()` 会先校验数据质量：只有有效指标的全局权重覆盖率至少为 `0.80`，且
`valuation`、`profit`、`growth`、`health` 四个核心维度均至少有一项有效指标时，才会
返回 `status: "ok"` 和评分结果。`None`、非数值、`NaN` 及正负无穷均不计入覆盖率；
数据不足时会返回缺失项信息且 `result` 为 `None`，不会暴露评级。

P1-01 的离线检查不需要 API key 或外部服务：

```bash
uv sync --all-groups
uv run pytest tests/unit/test_scoring_quality.py -q
uv run ruff check scoring.py tests/unit/test_scoring_quality.py
uv run mypy scoring.py
python3 scoring.py
```

## 📁 项目结构

```
ai-investment-copilot/
├── app.py            # Streamlit 主程序（三个功能 tab）
├── llm.py            # LLM / Embedding 调用封装
├── finance.py        # akshare 取数 + 技术指标计算
├── rag.py            # 极简 RAG：PDF 解析 / 切分 / 向量检索
├── requirements.txt
└── .env.example
```

## 🗺 路线图 (Roadmap)

- [ ] 接入实时新闻源，自动抓取并分析个股相关资讯
- [ ] 多轮对话记忆（Memory）
- [ ] 支持 ETF / 港美股
- [ ] 把 RAG 升级为持久化向量库（Chroma）
- [ ] 用 Next.js 重做前端，部署上线

## ⚠️ 免责声明

本项目仅用于技术学习与演示，所有 AI 输出**不构成任何投资建议**，据此操作风险自负。

---

*Built by 朱怡林 · 信息与计算科学*
