# 架构概览

## 当前已实现的过渡态

项目正在从单体 Streamlit 学习应用过渡为可独立演进的 API 与 Web 评分切片。以下组件已实现：

```text
Streamlit app.py / LangGraph agent.py ──> finance + scoring.score_stock (legacy compatibility)

Next.js /scoring ──POST /api/v1/scoring/evaluate──> FastAPI ──> scoring.evaluate_score
                                                        │
                                             /health/ready only
                                                        │
                                              PostgreSQL readiness check
                                                        │
                                             Alembic app_metadata baseline
```

- **Streamlit 兼容路径**：根目录 `app.py` 和 `agent.py` 仍提供旧的行情、LLM、RAG 与 `scoring.score_stock()` 调用方。它们是与 FastAPI 评分切片并存的 legacy 路径，可以读取本地模型配置，因而不是 API/前端离线测试的依赖。
- **FastAPI**：`backend.app.main:create_app` 暴露 `/api/v1` 健康检查和评分 API，负责 CORS、关联 ID 与安全错误信封。
- **评分领域适配层**：`backend/app/domain/scoring` 仅适配根目录的 `scoring.evaluate_score()`；没有复制或更改既有评分规则。它不调用 legacy `score_stock()`。数据不足时返回 `insufficient_data`，不暴露评级。
- **Next.js**：`frontend/` 仅实现评分表单和结果显示。客户端超时/取消/错误处理位于 API client；评分算法不在浏览器执行。
- **PostgreSQL/Alembic**：数据库基础设施是惰性创建的，`/health/ready` 检查连接和当前 Alembic revision。唯一的初始迁移创建 `app_metadata`；API 启动不会迁移数据库。
- **Compose**：基础拓扑包含 PostgreSQL、一次性 `migrate`、API、前端以及可选 `legacy` Streamlit profile。开发组合发布 `5432/8000/3000`；生产组合不发布 PostgreSQL 端口。

## 运行边界

`/health/live` 不依赖数据库，适合进程存活探针；`/health/ready` 只有在 PostgreSQL 可连接且已迁移时才准备就绪。评分 `POST /scoring/evaluate` 走 `evaluate_score()`，本身不查询数据库。Compose 将 API 启动置于成功迁移之后。Docker Engine 是运行/验收 Compose 的操作方前置条件，本主机没有把 Docker 构建或启动结果作为已验证交付。

环境变量通过本地 `.env`（Streamlit）或 `deploy/env/*.example` 的外部副本提供。真实凭据不进入 Git、镜像、工作流或示例文件。CI 只执行离线单元/API/前端检查；它不注入 API key、不调用模型，也不连接生产资源。

## 已规划但未交付的边界

以下是未来设计方向，不是当前实现：

- CrewAI 或其他多 Agent 编排、工作流 worker/队列与异步任务。
- 持久化 RAG、向量数据库、研报摄取/解析流水线。
- 认证、授权、租户隔离、审计、速率限制、密钥管理与完整安全运营能力。
- 生产发布自动化、可观测性平台、成本/模型评估及真实市场数据的可靠性治理。

新增这些能力应在独立设计与 PR 中明确数据流、权限、网络、成本和回滚边界，不能由当前 Compose 或 API 结构推断为已部署。
