# 本地开发环境

本仓库当前同时保留三条可独立启动的路径：原有 Streamlit 兼容界面、FastAPI 评分 API、以及 Next.js 评分页面。PostgreSQL/Alembic 是 API 的就绪检查与持久化基线；评分接口本身不需要模型调用。

## 前置条件

- macOS、Linux，或带有等效工具的 Windows 环境。
- [uv](https://docs.astral.sh/uv/) 和 CPython `3.12`；项目将 Python 限定为 `>=3.12,<3.13`。
- Node.js `24.18.0` 与 npm `11.16.0`（版本文件为 `frontend/.node-version`）。
- 仅在使用 Compose 或真实数据库时需要 Docker Engine 与 Docker Compose v2。

验证工具版本：

```bash
uv --version
uv python install 3.12
node --version
npm --version
docker compose version # 仅 Compose 路径需要
```

如使用 nvm，可按仓库版本文件安装并切换 Node：

```bash
nvm install "$(cat frontend/.node-version)"
nvm use "$(cat frontend/.node-version)"
npm install --global npm@11.16.0
```

## 安装依赖与离线检查

在仓库根目录执行：

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

这些检查不启动 Docker、PostgreSQL、外部模型或生产资源。数据库集成测试在未设置 `TEST_DATABASE_URL` 时会明确跳过；这不是数据库验收已经完成的声明。

## 启动开发服务

### FastAPI 评分 API

默认开发设置可启动存活检查和评分接口；未配置数据库时 `/api/v1/health/ready` 会返回安全的 `503 database_not_ready`。

```bash
uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

访问：

- 健康检查：`http://127.0.0.1:8000/api/v1/health/live`
- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`

### Next.js 评分页面

先启动 API，再在另一个终端运行：

```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm --prefix frontend run dev
```

打开 `http://localhost:3000/scoring`。默认 API CORS 来源也是
`http://localhost:3000`，请勿混用 `127.0.0.1` 作为前端地址。该页面只调用评分 API，
不在浏览器中复制评分算法。

### Streamlit 兼容路径

Streamlit 是仍受支持的旧界面。只有使用行情、LLM 或 RAG 功能时才需把 `.env.example` 复制为本地 `.env` 并填入自己的模型提供方配置；不要提交 `.env`：

```bash
cp .env.example .env
streamlit run legacy/app.py
```

默认地址为 `http://localhost:8501`。模型或行情连接失败时，先检查本地 `.env`、供应商权限和网络；它们不是离线 CI 的依赖。

## PostgreSQL 与迁移

对本机已运行的 PostgreSQL，设置仅限本地的连接串后手动迁移：

```bash
export DATABASE_URL='postgresql://investment_agent:local-password@127.0.0.1:5432/investment_agent'
uv run alembic -c backend/alembic.ini upgrade head
uv run alembic -c backend/alembic.ini current
```

当前唯一基线迁移创建 `app_metadata`。API 在启动时不会自动执行迁移；生产和 Compose 都由显式 `migrate` 步骤处理。

## Docker Compose（需 Docker）

Docker 是操作方前置条件。下列命令描述可在具备 Docker Engine 的环境中进行的验收流程；本主机未执行 Docker 构建或启动。

```bash
cp deploy/env/development.example /tmp/investment-agent.dev.env
docker compose --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml up --build
```

开发组合启动 PostgreSQL、一次性 Alembic 迁移、API 和 Next.js 前端，并发布 `5432`、`8000`、`3000`。可选旧界面：

```bash
docker compose --profile legacy --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml up --build
```

停止时使用：

```bash
docker compose --env-file /tmp/investment-agent.dev.env \
  -f deploy/compose.base.yml -f deploy/compose.dev.yml down
```

生产组合不发布 PostgreSQL 主机端口。将 `deploy/env/production.example` 复制到密钥管理位置，替换所有占位符后再使用，不要把生产文件放入仓库。

## 故障排查

| 现象 | 检查方式 |
| --- | --- |
| `uv` 使用了错误 Python | 重新执行 `uv python install 3.12` 和 `uv sync --locked --all-groups`。 |
| 前端安装或类型检查失败 | 确认 Node `v24.18.0`、npm `11.16.0`，然后重跑 `npm --prefix frontend ci`。 |
| API `/ready` 返回 503 | 确认 `DATABASE_URL` 可连接，执行 `alembic upgrade head`，并确认 `alembic_version` 为当前修订。 |
| API 端口已占用 | 使用其他端口启动 Uvicorn，并相应设置 `NEXT_PUBLIC_API_BASE_URL`。 |
| Compose 不可用 | 安装并启动 Docker Engine/Compose v2；在其可用前只运行上面的离线检查。 |
