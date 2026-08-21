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

## 第一阶段公开市场数据工具

以下端点是只读的 workspace 受保护工具，统一通过 `ToolRegistry` 执行，并保留
`source`、`as_of` 和 `missing_fields` 等数据边界字段：

- `POST /api/v1/market/quote`：批量读取 A 股实时行情；请求体为 `{"codes":["600519"]}`。
- `POST /api/v1/market/valuation`：读取行情、PE/PB 和当前年/下一年 EPS 预期及可复算派生值；请求体为 `{"symbol":"600519"}`。
- `POST /api/v1/market/financials`：读取最新报告期的营收、净利、EPS、ROE、毛利率、净利率和每股经营现金流；请求体为 `{"symbol":"600519"}`。
- `POST /api/v1/market/dossier`：按固定顺序组合上述三项数据，返回 `ready`、`partial` 或
  `unavailable` 底稿；每个 section 独立记录 `status`、`missing_fields` 和 `error_code`。
- `POST /api/v1/market/debate`：在同一份 Dossier 上顺序执行 `Bull → Bear → Moderator` 三次
  结构化模型调用，返回双方证据引用、共识、分歧、核验清单和数据缺口。该端点需要显式配置
  `AGENT_EXECUTION_MODE=openai_compatible`；默认 deterministic 模式返回 `503`，统一错误信封不会
  暴露内部 detail。

辩论输出仅允许比较底稿中的支持与反证，严格拒绝买入/卖出、目标价、仓位和评级等行动性内容；
直接调用接口时仍是非流式；通过 `workflow=market_debate` 创建 Agent Run 后，会写入角色事件并由既有 SSE 重放。

工具只返回公开观测和明确的缺失项，不生成买卖建议、目标价或预测。上游无可用数据时返回
`503`（统一错误信封中的 `http_error`）；参数、权限、超时仍使用统一错误边界。第一阶段已完成离线
fixture/API 测试，但尚未把联网 provider 验收作为交付证据。

## 开发期 Agent Run 与 SSE

阶段二提供持久化的研究任务资源：

- `POST /api/v1/research/tasks`：按 `target`、`research_type`、`depth`、`time_range` 和 `output_format` 创建专业研究任务；`time_range=custom` 必须同时提供 `custom_start` 与 `custom_end`。接口返回 `202` 和对应 Agent Run。
- `POST /api/v1/agent/runs`：创建任务，数据库写入后快速返回 `202`。请求可显式指定
  `workflow`：默认 `research` 保持原有流程；`market_debate` 需要同时提供 6 位 `symbol`，
  执行固定的 Dossier 与 `Bull → Bear → Moderator` 事件链。
- `GET /api/v1/agent/runs/{run_id}`：读取任务状态。
- `GET /api/v1/agent/runs/{run_id}/events`：返回 `text/event-stream`；事件的整数 `sequence` 是 SSE `id`，客户端可用 `Last-Event-ID` 只重放更晚事件。
- `GET /api/v1/research/{run_id}/stream`：研究产品的长连接执行流；在任务达到终态前持续轮询并推送持久化事件，事件同样使用 `sequence` / `Last-Event-ID`，`agent.trace` 的 `data.type` 为统一的 `PLANNING_START`、`TOOL_CALL_*`、`AGENT_*`、`REFLECTION_START` 或 `REPORT_GENERATE_START`。
- `GET /api/v1/agent/runs/{run_id}/report`：读取最近一次由 Report Agent 生成的机构报告；固定包含 11 个英文章节，每条报告结论都必须有数据支持、分析逻辑和引用。
- `GET /api/v1/agent/runs/{run_id}/report/export/{markdown|pdf}`：导出同一份机构报告内容，避免 Markdown 与 PDF 两套内容漂移。

知识库检索 `POST /api/v1/knowledge/search` 的每个 `results[]` 同时保留旧字段
`text`、`filename`、`page_number`，并提供统一溯源字段：
`content`（原文块）、`source`（来源名称）、`page`（页码）和 `date`（来源日期，暂无时为 `null`）。
机构报告的每条 `citations[]` 绑定 `evidence_id`、原文 `content`/`excerpt`、`source`、`page`、`date`，
以及可选 `source_url`。前端点击引用会打开原文摘录和定位信息；存在 URL 时可继续打开来源。

## 长期 Memory

- `GET /api/v1/memory/user`：读取当前 workspace/user 的关注行业、投资风格、风险偏好和历史关注股票。
- `POST /api/v1/memory/user`：显式保存或覆盖用户画像；身份和 workspace 从认证上下文取得，不由客户端提交。
- `GET /api/v1/memory/research`：读取历史研究任务/报告，可按 `symbol` 过滤。
- `POST /api/v1/memory/research`：保存一条历史研究记录。
- `POST /api/v1/memory/research/{memory_id}/feedback`：保存用户对历史研究的反馈。

Run 执行开始时 Planner 会读取同一 workspace/user 的 Memory。用户画像中包含 AI、人工智能、半导体或芯片关注项时，Planner 会记录 `user_memory:ai_interest`，并确保计划包含 AI 行业分析；历史研究记录会以 `research_memory:previous_reports` 标记并作为上下文传给 Analyst。Memory 只作为用户上下文，不能替代或伪装成 Citation。

## Agent Evaluation

- `GET /api/v1/evaluation/summary`：读取离线 JSONL 评测报告，适用于带标注的 Accuracy、Citation Score 等质量评测。
- `GET /api/v1/evaluation/runtime-summary`：读取当前 workspace/user 的真实 Agent Run 遥测，返回 `total_research`、`success_rate`、`average_latency_seconds`、`average_cost_usd`、`citation_score` 和 `tool_success_rate`。

运行时评测只从已持久化 Run、执行事件和模型成本字段计算；没有人工事实标注时 `accuracy` 保持 `null`，不会把任务完成率冒充事实准确率。前端 Evaluation 页面优先显示运行时指标，运行时接口不可用时回退到离线报告。

前端 Agent Run 面板已支持在“证据研究”和“市场事实辩论”之间切换；辩论事件会分别展示 Bull、Bear
和 Moderator，断线后沿用已有 `Last-Event-ID` 重连策略。前端测试使用 mock SSE，不代表真实浏览器、
PostgreSQL 或 Celery 已验收。
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
