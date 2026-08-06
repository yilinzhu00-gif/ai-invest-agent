# AI 投研助手（AI Investment Copilot）

面向个人投资者与金融学习者的研究辅助项目。当前处于从原有 Streamlit 学习应用向 FastAPI 评分 API、Next.js 评分页面与 PostgreSQL/Alembic 基线过渡的阶段。

> 本项目仅用于技术学习和研究辅助；所有输出均不构成投资建议，不保证数据完整性、及时性或收益，任何交易决定和风险由使用者自行承担。

## 当前已实现

| 路径 | 状态与用途 |
| --- | --- |
| Streamlit | `legacy/app.py` 是兼容入口；`legacy/` 集中保留原有行情、LLM、RAG 与评分实现，涉及模型/行情时需要本地配置。 |
| FastAPI | `backend.app.main:app` 提供 `/api/v1/health/live`、`/api/v1/health/ready` 与评分接口。 |
| 评分 API | `POST /api/v1/scoring/evaluate` 调用 `legacy/` 中保留的评分器；数据不足返回 `insufficient_data`，不会给出评级。 |
| Next.js | `frontend/` 提供 `/scoring`，只调用 API，不在浏览器重写评分规则。 |
| PostgreSQL/Alembic | 数据库就绪检查和 `app_metadata` 初始迁移已具备；API 不会在启动时自动迁移。 |
| Compose | 包含 PostgreSQL、一次性迁移、API、前端和可选 Streamlit profile 的架构定义。 |

CrewAI/多 Agent、持久化 RAG、worker/队列、认证授权、生产安全运营和发布自动化均尚未交付，不能视为现有能力。

## 前置条件

- CPython `3.12` 与 [uv](https://docs.astral.sh/uv/)
- Node `24.18.0`、npm `11.16.0`
- Docker Engine 与 Docker Compose v2（仅 Compose/真实 PostgreSQL 路径需要）

## 快速开始：离线开发检查

```bash
uv python install 3.12
uv sync --locked --all-groups
npm --prefix frontend ci

uv run ruff check .
uv run mypy backend/app legacy/scoring.py
uv run pytest -q
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

这些命令不启动 Docker、数据库、外部模型或生产资源。真实 PostgreSQL 集成测试需要显式提供 `TEST_DATABASE_URL`，否则会跳过。

## 本地服务

启动评分 API：

```bash
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

- API 存活检查：<http://127.0.0.1:8000/api/v1/health/live>
- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>

启动前端（先启动 API）：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm --prefix frontend run dev
```

打开 <http://localhost:3000/scoring>。默认 API CORS 来源也是
`http://localhost:3000`，请勿混用 `127.0.0.1` 作为前端地址。

Streamlit 兼容界面仅在需要旧功能时启动。复制 `.env.example` 为本地 `.env` 后填入自己的模型配置；切勿提交该文件或任何真实凭据：

```bash
cp .env.example .env
streamlit run legacy/app.py
```

## 数据库与 Compose

数据库迁移需要真实 PostgreSQL 与本地连接串：

```bash
export DATABASE_URL='postgresql://investment_agent:local-password@127.0.0.1:5432/investment_agent'
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

Compose 组合架构为 PostgreSQL → 一次性 `migrate` → FastAPI API → Next.js，外加可选 `legacy` Streamlit profile。Docker 是操作方验收的前置条件：本主机 Docker CLI 不可用，因此未在此主机执行 Docker 构建、启动或容器就绪验收。具备 Docker 后可按以下命令运行开发组合：

```bash
cp deploy/env/development.example /tmp/investment-agent.dev.env
docker compose --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml up --build
```

开发组合发布 `5432`、`8000`、`3000`；可选兼容 UI：

```bash
docker compose --profile legacy --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml up --build
```

生产组合不发布 PostgreSQL 到主机。使用 `deploy/env/production.example` 的变量名在密钥管理系统中创建外部环境文件，替换全部占位符后再执行生产操作。

## 文档

- [本地开发与排错](docs/development/local-setup.md)
- [Git 与 PR 流程](docs/development/git-workflow.md)
- [当前架构与边界](docs/architecture/overview.md)
- [API 契约](docs/api/overview.md)

## CI

PR 与相关的 `main` 推送会分别运行后端、前端和镜像构建检查。工作流仅使用 SHA 固定的 GitHub Actions、最小 `contents: read` 权限和非密钥包缓存；它们不注入 API key、不调用模型、不连接生产资源，也不推送镜像。
