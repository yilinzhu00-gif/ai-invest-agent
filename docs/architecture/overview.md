# 架构概览

## 当前已实现

项目由 API 服务与 Web 工作台组成，以下组件已实现：

```text
Next.js /scoring ──POST /api/v1/scoring/evaluate──> FastAPI ──> scoring.evaluate_score
                                                        │
                                             /health/ready only
                                                        │
                                              PostgreSQL readiness check
                                                        │
                                             Alembic app_metadata baseline
```

- **FastAPI**：`backend.app.main:create_app` 暴露 `/api/v1` 健康检查和评分 API，负责 CORS、关联 ID 与安全错误信封。
- **评分领域适配层**：`backend/app/domain/scoring` 调用服务端评分器，没有在 API 或浏览器复制既有评分规则。数据不足时返回 `insufficient_data`，不暴露评级。
- **Next.js**：`frontend/` 仅实现评分表单和结果显示。客户端超时/取消/错误处理位于 API client；评分算法不在浏览器执行。
- **PostgreSQL/Alembic**：数据库基础设施是惰性创建的，`/health/ready` 检查连接和当前 Alembic revision。唯一的初始迁移创建 `app_metadata`；API 启动不会迁移数据库。
- **Agent Run（阶段二开发边界）**：`agent_runs`、`agent_run_events` 和 `conversation_messages`
  保存 Run、顺序事件与用户消息；`/api/v1/agent/runs` 使用 SSE 重放已落库事件。当前
  `DevelopmentRunExecutor` 是显式 `development_only` 的进程内执行器，不能替代阶段三的队列或
  跨进程恢复机制；临时 header principal 仅用于本地 workspace 隔离测试。每次 Run 都会实际执行
  `Analyst → Validator → Reviewer`：Analyst 与 Reviewer 不可委派，Validator 是不可绕过的
  引用、数值和权限硬门；每个角色的开始/结束/修订上限都会以 `agent.*` 事件持久化。
- **公开行情快照（开发期）**：当 Run 提供 6 位 A 股代码时，执行器用 AkShare 读取最近最多
  6 个未复权日线数据，并将标的、日期、收盘、涨跌幅、日内区间与成交数据固化为唯一 Citation。
  `research.result` 事件只展示该观测快照及来源；它明确不预测未来走势，数据源不可用会使任务失败，
  不会用问题文本伪造行情结果。
- **确认式 Memory 与恢复**：`agent_memories` 不是自动“长期记忆”。仅当 Reviewer 到达
  `human_review`，任务才进入 `awaiting_confirmation`；人工批准后，最终摘要才按用户与工作区隔离
  写入 Memory，且其只能作为上下文、不能充当引用证据。Worker 将超时作为显式可重试故障并持久化
  重试事件，达到上限或其他失败后保留原问题和事件历史，等待人工调用恢复接口重新入队。
- **多 Agent 模型模式**：默认 `AGENT_EXECUTION_MODE=deterministic`，以证据原文生成保守草稿，
  适合离线开发；显式设为 `openai_compatible` 后，Analyst 和 Reviewer 分别使用 `CHAT_MODEL` 与
  `REVIEW_MODEL` 的 OpenAI-compatible 调用，并共享单 Run token/费用上限。该模式需要
  `MODEL_API_KEY`（也兼容已有的 `OPENAI_API_KEY`）；没有接入真实文档检索时，输入证据仍仅为
  Run 的当前受控来源，不能宣称为完整研报研究。
- **模型边界（阶段二开发边界）**：`backend/app/models` 提供 `ModelGateway`、OpenAI-compatible
  adapter 和 `LegacyModelAdapter` 回滚路径；Prompt 文件按 ID/版本/SHA 记录，模型调用的 token、费用
  和延迟使用统一 usage 契约。离线测试只使用 mock，不调用付费 provider。
- **Compose**：基础拓扑包含 PostgreSQL、一次性 `migrate`、API 与前端。开发组合发布 `5432/8000/3000`；生产组合不发布 PostgreSQL 端口。

## 运行边界

`/health/live` 不依赖数据库，适合进程存活探针；`/health/ready` 只有在 PostgreSQL 可连接且已迁移时才准备就绪。评分 `POST /scoring/evaluate` 走 `evaluate_score()`，本身不查询数据库。Compose 将 API 启动置于成功迁移之后。Docker Engine 是运行/验收 Compose 的操作方前置条件，本主机没有把 Docker 构建或启动结果作为已验证交付。

环境变量通过 `deploy/env/*.example` 的外部副本提供。真实凭据不进入 Git、镜像、工作流或示例文件。CI 只执行离线单元/API/前端检查；它不注入 API key、不调用模型，也不连接生产资源。

## 已规划但未交付的边界

以下是未来设计方向，不是当前实现：

- 持久化 RAG、向量数据库、研报摄取/解析流水线。
- 认证、授权、租户隔离、审计、速率限制、密钥管理与完整安全运营能力。
- 生产发布自动化、可观测性平台、成本/模型评估及真实市场数据的可靠性治理。

新增这些能力应在独立设计与 PR 中明确数据流、权限、网络、成本和回滚边界，不能由当前 Compose 或 API 结构推断为已部署。
