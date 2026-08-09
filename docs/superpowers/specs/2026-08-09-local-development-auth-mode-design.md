# 本地研究任务开发身份模式设计

## 目标

让 `/agent-runs` 在本地开发环境可以直接创建、恢复、订阅和取消研究任务，同时保持生产环境的 OIDC、workspace membership 与权限校验不变。

本次只修复前端与现有开发 API 的身份协议不一致，不接入真实行情、外部模型或新的研究 Agent。开发执行器仍明确显示为 `development_only`。

## 方案

新增显式公开配置 `NEXT_PUBLIC_AUTH_MODE`，允许值为 `oidc` 或 `development`：

- `oidc`：保留现有 Authorization Code + PKCE 流程，研究请求发送 `Authorization: Bearer ...` 与 `X-Workspace-ID`。
- `development`：不初始化 OIDC 客户端，使用 `NEXT_PUBLIC_DEVELOPMENT_PRINCIPAL_ID` 与 `NEXT_PUBLIC_DEFAULT_WORKSPACE_ID` 生成 `X-Development-Principal-ID` 和 `X-Development-Workspace-ID`。

`NEXT_PUBLIC_AUTH_MODE` 必须显式设置为 `development` 或 `oidc`；缺失或空白值会产生 `configuration_error`。直接运行 `next dev` 与 Docker 开发组合都必须显式设置 `development`，避免依赖构建工具的隐式环境判断。生产示例显式设置 `oidc`。

后端安全边界不变：`APP_ENV=production` 时继续拒绝开发身份请求头，只有经过 OIDC JWT 校验且具备 workspace membership 与 `agent:run` 权限的主体可以创建研究任务。

## 组件改动

### 认证上下文

`AuthProvider` 增加认证模式与已构建请求头：

- 开发模式校验 principal/workspace 均为非空字符串，随后立即进入 `authenticated`。
- OIDC 模式继续校验 authority、client ID、workspace，并恢复或发起登录。
- 配置缺失时进入 `configuration_error`，不会静默降级到开发模式。

页面在开发模式显示“本地开发身份模式”提示，不显示登录或退出按钮。

### 研究任务请求

`AgentRunPanel` 不再自行假设所有请求都使用 OIDC token，而是消费认证上下文提供的请求头。创建、读取、SSE 和取消任务共用同一组请求头，避免恢复链与创建链行为不一致。

### 环境与文档

- Compose 将新的公开变量作为前端构建参数传入。
- `deploy/env/development.example` 提供非敏感本地 principal/workspace 示例。
- `deploy/env/production.example` 显式使用 OIDC。
- 本地开发文档说明 3000 是标准前端端口；临时改用 3001 时需同时把该来源加入 `CORS_ORIGINS`。

## 数据流

开发模式的数据流为：

`输入问题 -> AgentRunPanel -> 开发身份请求头 -> FastAPI development principal -> PostgreSQL -> DevelopmentRunExecutor -> SSE -> 页面事件列表`

OIDC 模式的数据流保持：

`OIDC 登录 -> Bearer token/workspace -> JWT 与 membership 校验 -> CeleryRunExecutor -> PostgreSQL/Redis/Worker -> SSE`

## 错误处理

- 缺失、空白或未知 `NEXT_PUBLIC_AUTH_MODE`：`configuration_error`。
- 开发 principal 或 workspace 缺失/空白：`configuration_error`。
- API 返回非成功状态：保留当前“无法创建/恢复/取消任务”提示。
- SSE 失败：任务仍保留，页面提示刷新后恢复。

## 测试与验收

先写失败测试，再实现：

1. `AuthProvider` 在显式开发模式下进入 authenticated，并生成两个开发请求头。
2. OIDC 模式配置缺失仍为 configuration error，不能降级。
3. `AgentRunPanel` 的创建请求在开发模式只发送开发身份头，不发送 Bearer token。
4. 既有 OIDC 请求头测试继续通过。
5. 前端 lint、typecheck、全量测试与 build 通过。
6. 后端全量测试通过，确认生产身份边界未改变。
7. 使用本地 API 和浏览器实际创建一条 `development_only` 任务，观察 SSE 到达 completed。

## 不做

- 不创建本地 Keycloak/Dex。
- 不绕过生产 OIDC/JWT/membership/permission 校验。
- 不把开发身份变量当作密钥。
- 不接入真实行情、新闻、RAG 或模型 Provider。
- 不改变阶段四预研门禁或部署架构。
