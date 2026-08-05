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

请求体只接受 `symbol`、`as_of_date` 和 `metrics`，不允许额外字段。`symbol` 是 6 位 ASCII 数字，`as_of_date` 是严格的 `YYYY-MM-DD` 日历日期，`metrics` 最多包含 100 项。

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
| 404 或其他 HTTP 错误 | `http_error` | 未匹配的 HTTP 路由/方法。 |
| 422 | `validation_error` | 请求体不符合评分契约。 |
| 503 | `database_not_ready` | 数据库未配置、不可用或迁移状态不匹配。 |
| 500 | `internal_server_error` | 未预期服务端错误，使用关联 ID 排查。 |

此 API 为研究辅助工具，不构成投资建议，也不保证数据完整性、及时性或收益。
