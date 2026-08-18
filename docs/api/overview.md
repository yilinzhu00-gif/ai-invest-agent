# API 概览

API 基础前缀为 `/api/v1`。当前没有认证端点或访问控制；不要把本地开发 API 暴露到不受控网络。运行 FastAPI 后可访问：

- OpenAPI JSON：`/openapi.json`
- Swagger UI：`/docs`

## 健康检查

### `GET /api/v1/health/live`

进程存活检查，不连接数据库。

```json
{"status":"healthy","version":"0.1.0"}
```

### `GET /api/v1/health/ready`

就绪检查会连接 PostgreSQL 并确认 `alembic_version` 等于当前应用 revision。未配置、不可连接或未迁移的数据库返回 `503` 错误信封；这与 `/live` 成功并不矛盾。

```json
{"status":"ready","version":"0.1.0"}
```

## 评分

### `POST /api/v1/scoring/evaluate`

请求体只接受 `symbol`、`as_of_date` 和 `metrics`，不允许额外字段。`symbol` 是 6 位
ASCII 数字，`as_of_date` 是严格的 `YYYY-MM-DD` 日历日期，`metrics` 最多包含 100 项。
每个指标值必须是有限 JSON 数字或显式 `null`；字符串、布尔值、对象和数组均返回
`422 validation_error`。默认最大请求体为 64 KiB，声明长度或流式接收超过上限都会返回
`413 request_body_too_large`。

```json
{
  "symbol": "600519",
  "as_of_date": "2026-08-05",
  "metrics": {
    "pe_ttm": 18.5,
    "pb": 2.3,
    "roe": 16.2,
    "net_margin": 12.5,
    "gross_margin": 38.0,
    "rev_growth": 22.0,
    "profit_growth": 28.0,
    "debt_ratio": 45.0,
    "current_ratio": 1.8,
    "ret_60d": 8.0,
    "price_vs_ma20": 3.5
  }
}
```

成功且数据充分时，响应的 `status` 为 `ok`，`result` 包含 `total`、`grade`、`label`、各维度及指标明细。`coverage` 是有效指标权重覆盖率，`missing_core_dimensions` 和 `missing_metrics` 显示质量门诊断。

下例为 `result.dimensions` 的结构节选；数据充分时实际响应会返回每个有效评分维度及其指标明细，而不是空数组。

```json
{
  "status": "ok",
  "coverage": 1.0,
  "missing_core_dimensions": [],
  "missing_metrics": [],
  "result": {
    "total": 79.9,
    "grade": "B",
    "label": "看好",
    "dimensions": [
      {
        "name": "估值",
        "score": 77.8,
        "weight": 0.2,
        "weight_norm": 0.2,
        "contribution": 15.6,
        "metrics": [
          {
            "name": "PE(TTM)",
            "value": 18.5,
            "subscore": 82.2,
            "weight": 0.6,
            "weight_norm": 0.6
          }
        ]
      }
    ]
  }
}
```

数据不足时 HTTP 状态仍为 `200`，但业务状态为 `insufficient_data` 且 `result` 必为 `null`；客户端不得显示总分或评级。

```json
{
  "status": "insufficient_data",
  "coverage": 0.1,
  "missing_core_dimensions": ["profit", "growth", "health"],
  "missing_metrics": ["..."],
  "result": null
}
```

## 开发期 Agent Run 与 SSE

阶段二提供持久化的研究任务资源：

- `POST /api/v1/agent/runs`：创建任务，数据库写入后快速返回 `202`。
- `GET /api/v1/agent/runs/{run_id}`：读取任务状态。
- `GET /api/v1/agent/runs/{run_id}/events`：返回 `text/event-stream`；事件的整数 `sequence` 是 SSE `id`，客户端可用 `Last-Event-ID` 只重放更晚事件。
- `POST /api/v1/agent/runs/{run_id}/cancel`：幂等取消；终态不会被逆转。
- `POST /api/v1/agent/runs/{run_id}/confirm`：仅当任务处于 `awaiting_confirmation` 时，
  由人工批准或拒绝 Human Review 结果。批准才会保存一条可复用 Memory。
- `POST /api/v1/agent/runs/{run_id}/recover`：人工把 `failed` 任务重新入队；执行器从已持久化的
  问题、事件历史和同一用户/工作区的已确认 Memory 重新开始。

页面创建公开 A 股行情研究时应同时提供 6 位 `symbol`，例如：

```json
{"symbol":"600519","question":"贵州茅台股价走势"}
```

`symbol` 会与 Run 一起持久化，以便恢复时请求同一标的。开发期执行器经 AkShare 读取最近最多
6 个交易日的**未复权日线快照**，将其转换为带来源、标的和日期定位信息的 Citation；成功时额外
持久化 `research.result` SSE 事件，包含收盘价、涨跌幅、日内高低、成交量/额、最近收盘价列表和
“不预测未来走势”的边界说明。公开数据源不可用时任务会以 `market_data_unavailable` 失败并提供
恢复入口，绝不以用户问题或陈旧缓存冒充行情。

当前执行器响应中明确标记为 `development_only`。它将事件先持久化到 PostgreSQL，再由 SSE
读取；它不是生产队列，进程崩溃后只能查询/重放已落库的数据，阶段三将用独立 Worker 替换。
本阶段没有生产认证：本地开发和接口测试必须提供显式的
`X-Development-Principal-ID` 与 `X-Development-Workspace-ID`，它们仅用于临时 workspace
隔离测试，不能视为 OIDC、RBAC 或 RLS。

事件包含 `run.started`、`step.started`、`agent.analyst.*`、`agent.validator.*`、
`agent.reviewer.*`、`agent.flow.*`、`text.delta`、`research.result`、`review.required`、
`run.awaiting_confirmation`、`memory.saved`、`run.recovery_required`、终态事件和 `heartbeat`。
其中 `agent.*` 仅包含角色状态、结论和计数，不重复写入草稿或证据正文。事件历史读取结束后返回
heartbeat，客户端据此重连；不使用 WebSocket。

`agent_memories` 只保存人工批准后的最终摘要，按 `workspace_id + principal_id` 查询，最多注入
最近 8 条。它们是用户上下文，不是事实证据，不能作为 Citation 支撑结论；拒绝、人为取消、失败和
未确认的草稿都不会写入 Memory。生产 Worker 对 `run_timeout` 等显式瞬时错误按
`AGENT_RUN_MAX_RETRIES` 进行有界退避重试；耗尽后事件会提示人工调用 `/recover`，不会静默无限重跑。

## 错误与关联 ID

错误响应使用稳定信封，避免返回校验细节、异常消息、连接串或堆栈：

```json
{
  "error": {"code": "validation_error"},
  "correlation_id": "request-id"
}
```

客户端可在请求头提供 `X-Correlation-ID`；服务会在响应头返回同一 ID，并在错误信封中返回该值。未提供时服务生成 UUID。常见状态/代码：

| HTTP 状态 | `error.code` | 含义 |
| --- | --- | --- |
| 400 | `cors_preflight_rejected` | CORS 预检来源或方法不被允许。 |
| 413 | `request_body_too_large` | 请求体超过默认 64 KiB 上限。 |
| 404 或其他 HTTP 错误 | `http_error` | 未匹配的 HTTP 路由/方法。 |
| 422 | `validation_error` | 请求体不符合评分契约。 |
| 503 | `database_not_ready` | 数据库未配置、不可用或迁移状态不匹配。 |
| 500 | `internal_server_error` | 未预期服务端错误，使用关联 ID 排查。 |

此 API 为研究辅助工具，不构成投资建议，也不保证数据完整性、及时性或收益。
