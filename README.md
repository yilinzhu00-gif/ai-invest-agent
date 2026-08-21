# Enterprise-level Multi-Agent Investment Research Platform powered by LLM

面向 A 股公告与研报阅读的企业级、多 Agent、证据驱动投资研究平台。它把研究材料、问题、引用、审核决定和导出简报放在一条可追溯的工作流里，而不是根据模型记忆直接给出结论。

## 核心能力

- ✅ Multi-Agent Collaboration
- ✅ Planning
- ✅ Tool Use
- ✅ Memory
- ✅ Reflection
- ✅ RAG
- ✅ Agent Evaluation
- ✅ MCP Integration
- ✅ Production Deployment

> 本项目仅用于研究辅助和技术学习，不构成投资建议、收益承诺或交易指令。任何投资决定及其风险由使用者自行承担。

## 现在能做什么

| 能力 | 当前行为 |
| --- | --- |
| 证据库 | 上传公告、研报或其他材料，保存文件版本、来源链接、页码与可检索文本块。 |
| 自由研究问题 | 选择一份材料并填写六位股票代码和任意研究问题；系统只从选定材料中检索证据。 |
| 交易事实表 | 对已解析的公告提取可定位原文的交易事实，不用模型常识补齐缺失字段。 |
| 市场反应 | 以公告日为锚点计算事件窗口、相对沪深 300 与研究员指定行业指数的表现。 |
| 证据门控研究 | Analyst 起草，独立数值校验器检查引用和计算，Reviewer 逐一检查“结论—引用”对应关系。 |
| 人工审核 | 证据不足时直接拒绝；审阅不完整或需要修订时进入人工审核，研究员可接受或驳回观点。 |
| 研究简报 | 研究员编辑后保存不可变版本，并导出 Markdown、PDF 或 Word；导出内容保留来源、页码、数据日期、内容指纹和风险声明。 |
| 股票评分 | 独立的手工指标评分页，不会替代公告或研报中的证据引用。 |

### Phase 1/2 数据工具与 Planner

Phase 1 的通用数据入口位于 `backend/app/tools/`（同时提供 `tools/` 顶层兼容导入）：

- `get_stock_price("AAPL")`：当前价格、涨跌幅、市场概值、PE 和 OHLCV K 线；
- `get_financial_report("AAPL")`：财报期、营收、利润、毛利率、增长率、EPS 和经营现金流；
- `search_news("英伟达 最近新闻")`：返回带标题、摘要、来源、日期和 URL 的新闻条目；
- `search_web("AI 芯片 竞争格局")`：返回来源可追溯的通用搜索结果。

这些入口默认使用无密钥公共 provider，并在 `data_registry.py` 中按只读权限、超时和每 Run 调用次数注册；公网 provider 不可用时会返回明确的 unavailable 错误，不会伪造数据。现有 A 股 `market.*` 三工具注册表保持兼容不变。

Phase 2 的 `backend/app/agents/planner.py` 提供 `build_planner_graph()` 和 `plan_with_langgraph()`。对“分析英伟达投资价值”这类投资问题，Planner 会输出公司基本面、AI 行业趋势、竞争格局、估值和风险五个结构化步骤；Planner 只负责拆解，不声称后续数据任务已完成。

当前 Phase 2 六角色图位于 `backend/app/agents/multi_agent.py`，节点顺序固定为：

```text
Planner
  -> Financial Analyst（财报、盈利能力、成长性）
  -> Industry Analyst（行业趋势、竞争格局、市场空间）
  -> Market Analyst（价格趋势、技术/估值观测、市场情绪）
  -> Debate（Bull / Bear / Moderator）
  -> Reflection（accuracy、logic、missing）
```

可通过 `run_multi_agent_research(...)` 或异步的 `arun_multi_agent_research(...)` 运行。图不会隐式联网；调用方应先通过 Phase 1 工具获取数据并传入 `financial_report`、`industry_data`、`stock_data`、`market_data` 及 Citation。这样可以在 provider 不可用时明确输出数据缺口，而不是把模型记忆伪装成引用。

## 研究主链路

1. 在 **证据库** 上传并确认材料已解析完成。
2. 在 **研究任务** 选择材料，输入股票代码和自由描述的问题。
3. 系统从所选材料检索原文；每条证据都带有文件名、版本、页码和文本块标识。
4. Analyst 生成草稿，数值校验器核验每个数字与计算，Reviewer 覆盖每一个“结论—引用”对。
5. 关键公告证据缺失时，任务进入 `rejected`，不会以行情、记忆或常识替代原文。需要人工判断时，任务进入 `awaiting_confirmation`。
6. 研究员可编辑简报、接受或驳回观点，保存版本后导出。

公告证据简报使用固定结构：

- 已证实的交易事实
- 公告后的市场反应
- 可能的影响机制
- 正面因素
- 风险和不确定性
- 尚缺少的信息
- 结论置信度

## 支持的材料与边界

- 文件大小上限为 50 MiB，页数上限为 500 页。
- PDF、Markdown、HTML 与 CSV 可直接解析；DOCX、XLSX、PPTX 和图片需安装 `document-worker` 可选依赖；扫描件还需要配置 OCR Worker。
- 当前研究任务不会自行抓取任意网页或替换用户选择的材料。没有直接证据，就不生成对应结论。
- 本地开发身份模式会读取公开日线行情快照，但不会调用生产模型；生产环境需要 PostgreSQL、Redis/Celery 和 OIDC 配置。

## 技术架构

```text
Next.js 工作台
    │ HTTP / SSE
FastAPI API ── PostgreSQL（材料、引用、任务、简报版本）
    │
Redis / Celery Worker（生产环境的异步任务）
```

- 前端：Next.js 15、React 19、TypeScript
- 后端：FastAPI、SQLAlchemy、Alembic、PostgreSQL/pgvector
- 异步任务：Redis、Celery（生产环境）
- Agent：LangGraph 为默认运行时；CrewAI 保留为兼容运行时
- 认证：本地开发身份模式或生产 OIDC；生产接口按 workspace 与权限校验

### Phase 4 RAG 知识库（本地可运行切片）

`backend/app/rag/` 提供一条不依赖网络的最小闭环：`loader.py` 按 PDF 页码或文本文件切块并保留
来源元数据，`embedding.py` 默认使用确定性的本地特征哈希（可显式替换为 OpenAI-compatible
embedding provider），`retriever.py` 建立向量索引并执行 cosine 检索、workspace/主体 ACL 过滤和
页码引用渲染。上传接口可登记财报、公告、券商研报、行业报告和政策文件，标的代码可选（例如
`600519` 或 `NVDA`）；未指定 `document_id`
的 research Run 会先检索当前 workspace 的材料，只有没有命中时才回到原行情快照或证据不足边界。

```python
from backend.app.rag import RAGRetriever, load_document

retriever = RAGRetriever()
retriever.index(load_document("annual-report.pdf", document_type="financial_report"))
evidence = retriever.retrieve("为什么英伟达护城河强？", top_k=5)
```

默认哈希 embedding 只用于本地开发和离线评估；它不是已证明的语义模型质量，也不代表生产
pgvector 索引、真实券商/行业材料或云端模型已经部署。

### Phase 0 分层约定

后端的新代码按 API、agents、services、rag、memory、evaluation、config
分层；现有 `domain/`、`tools/`、`core/` 和 `evals/` 作为已验证实现，由这些
入口通过适配层复用。向量存储当前选择 PostgreSQL/pgvector（部署镜像已提供），
Chroma/Milvus 保留为后续可替换 provider，不在本阶段引入第二套运行时。

## Phase 8：部署与工程化

Compose 将应用拆为可独立扩缩和观测的服务边界：

| 服务 | 责任 | 默认端口 |
| --- | --- | --- |
| `frontend` | Next.js 研究工作台 | 3000 |
| `backend` | FastAPI API（网络兼容别名 `api`） | 8000 |
| `postgres` | 研究材料、Run、审核和迁移数据 | 5432（仅开发映射） |
| `redis` | Celery 队列与缓存 | 内部网络 |
| `vector-db` | 独立 pgvector 存储边界 | 内部网络 |

本地启动仍使用根目录入口：

```bash
cp deploy/env/development.example /tmp/investment-agent.dev.env
docker compose --env-file /tmp/investment-agent.dev.env up --build
```

GitHub Actions 的 Phase 8 工作流为 `push → test → build image → deploy`：后端、前端和 Compose 合约先通过测试，随后以 commit SHA 构建并推送 GHCR 镜像；只有仓库变量 `DEPLOY_ENABLED=true` 且 `production` 环境已配置 SSH/主机 secrets 时才执行远端 Compose 更新和 HTTPS smoke test。当前仓库提供的是可审计的部署契约，不把未配置的云账号、OIDC、镜像仓库或线上运行结果冒充为已验证生产部署。

## 快速启动（推荐：Docker Compose）

前置条件：Docker Engine + Docker Compose v2。

```bash
cp deploy/env/development.example /tmp/investment-agent.dev.env
docker compose --env-file /tmp/investment-agent.dev.env up --build
```

启动后打开：

- 工作台：<http://localhost:3000>
- API 健康检查：<http://localhost:8000/api/v1/health/live>
- OpenAPI：<http://localhost:8000/docs>

上述配置仅用于本地开发，使用本地开发身份，不应作为生产部署配置。

## 本地开发

前置条件：CPython 3.12、[uv](https://docs.astral.sh/uv/)、Node 24.18.0、npm 11.16.0。

```bash
uv python install 3.12
uv sync --locked --all-groups
npm --prefix frontend ci
```

Python 依赖只以 `pyproject.toml` 与 `uv.lock` 为准；前端依赖只以 `frontend/package.json` 与 `frontend/package-lock.json` 为准。

运行质量检查：

```bash
uv run ruff check .
uv run mypy backend/app
uv run pytest -q
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

如果不使用 Compose，需要自行提供 PostgreSQL、Redis、`DATABASE_URL` 和前端环境变量。数据库迁移命令为：

```bash
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

## 配置说明

| 场景 | 配置文件 | 认证方式 |
| --- | --- | --- |
| 本地 Compose | `deploy/env/development.example` | 开发身份 |
| 一般生产部署 | `deploy/env/production.example` | OIDC |
| 单机部署 | `deploy/env/single-node.example` | OIDC + Nginx/HTTPS |

不要提交实际的 `.env`、数据库密码、OIDC 客户端密钥或 TLS 证书。示例文件仅提供变量名和本地占位值。

## 目录说明

```text
backend/       FastAPI、Agent 流程、分层服务、数据模型、迁移与测试
frontend/      Next.js 工作台与前端测试
docker/        容器边界说明与本地运行约定
deploy/        Compose 服务定义、环境变量模板和部署配置
docs/          架构、API、开发、运维与回滚文档
evals/         离线评估输入与基准
load/k6/       k6 压测脚本
legacy/        仍被股票评分路径使用的兼容代码
artifacts/     本地生成的评估产物（已忽略，不提交）
scripts/       运维和验证脚本
tests/         顶层兼容性测试
```

`.venv`、`__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`frontend/node_modules` 和 `frontend/.next` 都是本地生成内容，不应提交。

## 相关文档

- [架构与边界](docs/architecture/overview.md)
- [API 概览](docs/api/overview.md)
- [本地开发与排错](docs/development/local-setup.md)
- [部署说明](docs/operations/deployment.md)
- [备份与恢复](docs/operations/backup-restore.md)
- [回滚 Runbook](docs/runbooks/rollback.md)

## CI

GitHub Actions 会对相关改动运行后端检查、前端检查、离线 Agent 评估、容器构建与依赖安全扫描。`phase8-deploy.yml` 在 `main` push 上以 commit SHA 构建并推送 GHCR 镜像；部署 job 默认关闭，只有 `production` 环境和 `DEPLOY_ENABLED=true` 显式开启后才会连接运维主机。工作流不注入模型密钥、不调用生产模型。
