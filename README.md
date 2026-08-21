# 投研研究工作台

面向 A 股公告与研报阅读的证据驱动研究辅助系统。它把研究材料、问题、引用、审核决定和导出简报放在一条可追溯的工作流里，而不是根据模型记忆直接给出结论。

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

## 快速启动（推荐：Docker Compose）

前置条件：Docker Engine + Docker Compose v2。

```bash
cp deploy/env/development.example /tmp/investment-agent.dev.env
docker compose --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml up --build
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
backend/       FastAPI、Agent 流程、数据模型、迁移与测试
frontend/      Next.js 工作台与前端测试
deploy/        Compose、环境变量模板和部署配置
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

GitHub Actions 会对相关改动运行后端检查、前端检查、离线 Agent 评估、容器构建与依赖安全扫描。工作流不注入模型密钥、不调用生产模型，也不推送镜像。
