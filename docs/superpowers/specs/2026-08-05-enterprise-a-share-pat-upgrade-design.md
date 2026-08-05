# 企业级 A 股 PAT 投研系统升级设计

**日期：** 2026-08-05

**状态：** 总体设计已获用户批准，待书面规格复核

**目标读者：** 产品负责人、投研负责人、后端工程师、Agent 工程师、数据工程师、审核员

## 1. 目标

把当前面向个人学习的 Streamlit + LangGraph 投研 Demo，升级为内部团队使用的企业级 A 股投研系统。升级后的系统必须具备：

- Chat Agent 与 Coding Agent 的职责、状态和运行进程隔离；
- “The plan is the analysis”：以版本化、可验证的 ResearchPlan 作为唯一执行契约；
- 标准算子与沙箱代码生成并存的混合编译能力；
- Task 级并行编译、DAG 分层执行、内容寻址缓存和失败恢复；
- 由普通 Python 强制执行的数据、Schema、数值、证据和报告质量门；
- 分析师、审核员、管理员三角色与 Workspace 级数据隔离；
- 公开市场数据、团队内部资料及未来商业数据源的统一接入；
- Autonomous Audit 与 Explicit Teach 双入口的 human-audited benchmark 学习飞轮；
- 从研究问题到发布报告的全链路版本、证据、审批和审计记录。

系统第一版只服务内部团队，聚焦标准化 A 股个股深度报告，不直接连接交易系统，不输出自动交易指令。

## 2. 已确认的产品决策

| 决策项 | 已选方案 |
|---|---|
| 产品形态 | 企业级内部团队多用户系统 |
| 研究范围 | A 股个股 |
| 数据范围 | 公开市场数据 + 团队内部研报、纪要和研究资料 |
| 数据扩展 | 通过适配器预留 Wind、Choice、Tushare Pro 等商业数据源 |
| 角色 | 分析师、审核员、管理员 |
| 首版交付 | 标准化深度个股报告 |
| 系统形态 | 模块化单体 + 独立异步 Worker |
| Coding Agent | 混合编译：标准算子优先，新任务进入沙箱代码生成 |
| 前端迁移 | 暂时保留 Streamlit，但所有数据和业务操作必须经过 FastAPI |
| 学习机制 | Autonomous + Explicit Teach + 人工审核 Benchmark + 受控发布 |

## 3. 范围边界

### 3.1 首版范围

- A 股单公司行情、技术面、基本面、成长、估值、研报证据和风险分析；
- 一家公司与可配置基准指数或同行的有限比较；
- 结构化 ResearchPlan、Task DAG、DataFrame Schema 和验收规则；
- 受控算子执行和新 Task 的受限 Python 函数生成；
- 交互式图表、结构化报告、审核、发布、归档；
- Workspace、RBAC、文档 ACL、审计日志；
- 失败 Benchmark、Context/Prompt/算子/校验器版本化升级。

### 3.2 首版明确不做

- 公开注册、计费、套餐、支付和外部 SaaS；
- 全球宏观、多资产、期权和衍生品研究；
- 组合优化、自动选股、策略回测和实盘交易；
- 不受限制的任意 Python、Shell、网络或文件系统访问；
- 无人工审核的自动知识发布；
- 用未经本项目 Benchmark 验证的方式宣称“四倍提速”“95% 确定性”等指标。

## 4. 总体架构

系统采用一个仓库内的模块化单体，并把异步分析执行放入独立 Worker 进程。逻辑组件如下：

```text
Streamlit Team UI
        |
        v
FastAPI Gateway
  |-- Authentication / OIDC
  |-- Workspace + RBAC
  |-- Research API
  |-- Review / Publish API
  |-- Teach / Benchmark API
  |-- Audit API
        |
        +--------------------+
        |                    |
        v                    v
Chat Agent Service      PostgreSQL + pgvector
        |                    |-- users/workspaces/ACL
        | ResearchPlan       |-- conversations/plans/tasks/runs
        v                    |-- documents/chunks/citations
Plan Store / Queue           |-- reviews/benchmarks/audit events
        |
        v
Coding Agent Worker Pool <---- Redis broker/cache coordination
  |-- Operator Compiler
  |-- Sandboxed Code Compiler
  |-- DAG Scheduler
  |-- Validator
  |-- Artifact Writer
        |
        +--> Market Data Adapters
        +--> Document Retrieval
        +--> S3-compatible Object Storage
```

PostgreSQL 是业务状态的唯一事实来源。Redis 只承担任务投递、并发协调和短期缓存，不保存不可恢复的业务真相。PDF、原始数据快照、代码、DataFrame、图表和报告写入 S3 兼容对象存储，并在 PostgreSQL 中保存不可变版本与校验和。

## 5. 信任边界与双 Agent 分离

### 5.1 Chat Agent

Chat Agent 负责：

- 保存和续接投研对话；
- 理解 A 股投研术语、用户意图和研究目的；
- 查询 Data Catalog 和用户有权访问的文档目录；
- 识别缺失条件并提出澄清问题；
- 定义研究范围、假设、证据要求、DataFrame Schema、Task DAG 和验收规则；
- 发布不可变的 ResearchPlan 新版本；
- 在 Coding Agent 完成后，只基于已验证的 AnalysisArtifact 解释结果。

Chat Agent 禁止：

- 直接执行 Task 或修改 DataFrame；
- 绕过 Plan Gate 或 Validator；
- 修改已批准的 Plan 版本；
- 把未验证的工具错误当成正常证据；
- 读取当前用户权限之外的文档或产物。

### 5.2 Coding Agent

Coding Agent 负责：

- 消费已批准且通过 Plan Gate 的 ResearchPlan；
- 将每个 TaskSpec 编译为固定版本算子或受限 Python 函数；
- 并行编译互相独立的 Task；
- 按 DAG 层级执行任务；
- 写入缓存、DataFrame、图表、证据和 Validation Report；
- 在限定次数内修复可修复的生成代码；
- 对不可修复或不确定结果失败关闭。

Coding Agent 禁止：

- 读取完整对话历史来重新解释研究意图；
- 擅自增删 Task、放宽验收规则或更换数据权限；
- 在沙箱外执行生成代码；
- 直接发布报告或修改生产 Context。

### 5.3 唯一跨 Agent 契约

Chat Agent 到 Coding Agent 只传递版本化 `ResearchPlan`。Coding Agent 到 Chat Agent 只回传版本化 `AnalysisArtifact` 和 `ValidationReport`。两者不通过模块全局变量、共享内存或隐藏自然语言消息传递业务状态。

## 6. “The Plan Is the Analysis”

### 6.1 ResearchPlan

每个 ResearchPlan 是不可变版本，至少包含以下字段：

```yaml
plan_id: uuid
version: integer
workspace_id: uuid
created_by: uuid
question: string
asset:
  market: CN_A
  symbol: string
  display_name: string
as_of_date: YYYY-MM-DD
timezone: Asia/Shanghai
observation_window:
  start: YYYY-MM-DD
  end: YYYY-MM-DD
benchmark_symbols: [string]
research_objective: string
assumptions: [string]
exclusions: [string]
datasets: [DatasetRequirement]
frames: [DataFrameContract]
tasks: [TaskSpec]
acceptance_rules: [AcceptanceRule]
delivery_spec: DeliverySpec
context_version: string
status: PlanStatus
```

### 6.2 DatasetRequirement

每个数据要求必须声明：

- 逻辑数据集名称与数据类别；
- 首选和备用数据适配器；
- 证券、时间范围、频率、复权口径；
- 币种、单位、时区和发布日期口径；
- 必须字段、最大允许缺失率和最大允许陈旧时间；
- Workspace 和文档 ACL；
- 数据快照与来源版本要求。

### 6.3 DataFrameContract

每个输出 DataFrame 必须声明：

- `frame_id`、业务用途和生产 Task；
- 每列名称、数据类型、单位、币种和业务语义；
- 主键、唯一性、排序规则和关联键；
- 可空性、缺失率上限和数值范围；
- 时间列的时区与频率；
- 下游消费者和保留期限。

### 6.4 TaskSpec

每个 Task 大致对应一个纯 Python 函数和一个主要输出 DataFrame：

```yaml
task_id: string
name: string
description: string
dependencies: [task_id]
inputs: [frame_id]
output: frame_id
operator_hint: string | null
compilation_mode: AUTO | OPERATOR | GENERATED
parameters: object
acceptance_rules: [AcceptanceRule]
criticality: LOW | MEDIUM | HIGH
cache_policy: USE | REFRESH | DISABLE
```

### 6.5 Plan Gate

ResearchPlan 状态为：

```text
DRAFT
  -> NEEDS_CLARIFICATION
  -> READY_FOR_CONFIRMATION

READY_FOR_CONFIRMATION -> APPROVED
READY_FOR_CONFIRMATION -> READY_FOR_REVIEW
READY_FOR_REVIEW -> APPROVED | REJECTED
APPROVED -> SUPERSEDED
```

只有 `APPROVED` 版本可以创建 ResearchRun。进入 `APPROVED` 前必须满足：Schema 完整、DAG 无环、所有输入可解析、数据权限可满足、验收规则非空、交付规格完整。标准 Plan 在自动 Plan Gate 通过后由分析师明确确认；包含 `HIGH` 关键生成任务、敏感内部资料或管理员策略命中的 Plan 必须进入 `READY_FOR_REVIEW`，由审核员或管理员批准。缺失任一条件时不得由 Coding Agent 自行补猜。

## 7. 混合编译 Coding Agent

### 7.1 标准算子路径

已存在并审核的任务编译到带版本号的 `OperatorRegistry`。首版标准算子至少覆盖：

- A 股历史行情加载与复权；
- MA、RSI、收益率、波动率和成交量指标；
- 财务指标标准化；
- 估值、盈利、成长、财务健康和动量评分；
- 同行或指数比较；
- 文档检索与证据表；
- 基础统计、聚合、连接和缺失值报告；
- Plotly 图表规格生成；
- 报告表格与引用清单生成。

算子接口必须是纯函数语义：显式输入、显式参数、显式输出，不读取进程全局状态。

### 7.2 生成代码路径

无法由标准算子满足的新 Task 可以生成受限 Python 函数。统一函数契约为 `run_task(inputs: dict[str, pandas.DataFrame], params: dict[str, object]) -> pandas.DataFrame`。

首版生成代码只允许使用 Python 标准库中的纯计算模块、pandas 和 numpy。生成函数不得执行网络请求、直接文件 I/O、动态 import、`eval`、`exec`、子进程、环境变量读取、反射式模块访问或系统调用。

### 7.3 沙箱

每个生成 Task 在独立、非 root、无网络容器中执行，使用只读根文件系统和单独 tmpfs。沙箱必须限制 CPU、内存、运行时间、进程数和输出大小。输入由 Artifact Store 按授权和哈希注入；输出只能通过指定目录回收。

### 7.4 编译和修复状态

```text
PLANNED
  -> COMPILING
  -> STATIC_CHECKING
  -> SANDBOX_TESTING
  -> READY
  -> RUNNING
  -> VALIDATING
  -> SUCCEEDED

COMPILING | STATIC_CHECKING | SANDBOX_TESTING | RUNNING | VALIDATING
  -> RETRYABLE_FAILED
  -> FAILED
```

生成代码最多允许两次自动修复。第三次失败后 Task 进入 `FAILED`，ResearchRun 失败关闭并返回明确的错误类型、证据和人工处理建议。

### 7.5 确定性策略

- 数据输入使用不可变快照；
- 时间、随机种子、时区、依赖版本和执行镜像固定；
- 单个生成函数在相同输入上执行两次，比较归一化 DataFrame 哈希；
- `HIGH` 关键任务生成两个独立候选，并比较 Schema、主键集合、数值结果和语义标签；
- 浮点比较使用 Plan 明确给出的绝对或相对容差；
- 不一致时不得择一交付，必须修复或失败。

## 8. 并行编译、DAG 执行与缓存

Plan 已声明所有输入输出 Schema，因此无依赖 Task 可以在代码生成阶段并行编译。执行阶段只运行依赖均为 `SUCCEEDED` 或 `CACHE_HIT` 的 Task，并按拓扑层级并行。

ResearchRun 状态为：

```text
QUEUED -> COMPILING -> EXECUTING -> VALIDATING -> REPORTING
       -> AWAITING_REVIEW -> PUBLISHED

任一执行态 -> FAILED | CANCELLED
AWAITING_REVIEW -> REJECTED
```

报告被拒绝后，分析师必须根据原因创建新 Plan 版本或基于同一已批准 Plan 创建新的 ResearchRun；被拒绝的 Run 保持不可变。

缓存键至少包含：

- TaskSpec 规范化哈希；
- 输入 Artifact 哈希；
- 原始数据快照哈希；
- 算子版本或生成代码哈希；
- Python 和依赖环境版本；
- AcceptanceRule 版本。

只改变图表标题或报告措辞时，只重新执行交付层 Task。改变研究口径、数据时间点或上游计算时，自动失效受影响 Task 及其所有下游缓存。

## 9. 强制校验体系

校验器是普通 Python 代码和固定规则，不由 Agent 决定是否运行。校验至少分为：

1. **Schema 校验**：列、类型、主键、唯一性、排序、空值和单位；
2. **数据校验**：来源、时点、频率、复权、币种、陈旧度和覆盖率；
3. **数值校验**：范围、有限值、计算恒等式、容差和重复执行一致性；
4. **业务校验**：证券匹配、报告期匹配、同比/环比口径和财务字段语义；
5. **证据校验**：每项外部事实绑定文档页码或数据 Artifact；
6. **报告校验**：报告数字与上游 DataFrame 一致，失败和限制被明确披露；
7. **权限校验**：每个输入、输出和引用都处于当前 Workspace 授权范围。

结构化评分只有在以下条件同时满足时才能输出字母等级：

- 按 Plan 声明的指标权重计算，覆盖率至少为 80%；
- 估值、盈利、成长和财务健康四个核心维度各至少有一个有效指标；
- 所有评分输入都有来源、日期和单位；
- 没有未解决的字段语义冲突。

否则结果状态为 `INSUFFICIENT_DATA`，只展示已有事实和缺失项，不输出 A-E 评级。

## 10. 数据与 RAG

### 10.1 市场数据适配器

统一适配器接口覆盖行情、财务、估值和证券主数据。首版提供 AkShare 适配器，但业务层不得依赖 AkShare 中文列名。适配器必须把响应转换为规范化 Schema，并记录：

- `source`、`source_version`、`fetched_at`、`as_of_date`；
- `currency`、`unit`、`frequency`、`adjustment`；
- 原始响应校验和、授权范围和异常列表。

禁止静默吞掉数据异常。备用适配器失败后必须形成可见的 DataQualityReport。

### 10.2 文档接入与检索

- PDF 和文本按 Workspace ACL 入库；
- 每个 Chunk 保留文档、版本、页码、标题和段落位置；
- 先做权限过滤，再执行关键词与向量混合检索；
- 使用 pgvector 保存向量，使用 PostgreSQL 全文索引做关键词召回；
- 对候选结果重排，并将检索分数与来源元数据交给证据校验器；
- 报告引用必须能回到原文页码；
- 文档删除或权限收回后，后续运行不得继续检索，但历史已发布报告保留当时的权限审计和快照引用。

## 11. 多用户、Workspace 与权限

认证采用 OIDC 优先的内部登录方式，本地开发环境允许受控的种子账号。所有业务表都必须带 `workspace_id`，所有查询都必须由后端注入用户与 Workspace 条件，不能依赖前端过滤。

| 能力 | 分析师 | 审核员 | 管理员 |
|---|---:|---:|---:|
| 创建对话、Plan 和 Run | 是 | 是 | 是 |
| 上传 Workspace 文档 | 是 | 是 | 是 |
| 查看自己有权访问的研究 | 是 | 是 | 是 |
| 确认通过自动 Gate 的标准 Plan | 是 | 是 | 是 |
| 批准 HIGH 或敏感 Plan | 否 | 是 | 是 |
| 审核或驳回报告 | 否 | 是 | 是 |
| 审核 Benchmark 预期 | 否 | 是 | 是 |
| 发布 Context/算子/校验器版本 | 否 | 否 | 是 |
| 管理用户、角色、数据源和 ACL | 否 | 否 | 是 |
| 查看全 Workspace 审计 | 否 | 是 | 是 |

当前 `agent.py` 的模块全局 `_CURRENT_STORE` 必须移除。任何文档 Store、对话状态或缓存都必须以 `workspace_id`、`user_id` 和资源 ACL 定位。

## 12. 报告、审核与交付

标准个股报告至少包含：

1. 研究问题、as-of 日期与数据范围；
2. 一句话结论和置信边界；
3. 行情与技术面；
4. 基本面与成长；
5. 估值与相对比较；
6. 内部/外部研究证据；
7. 主要风险、反例和数据限制；
8. 交互式图表；
9. 数据覆盖率与 Validation Report 摘要；
10. Plan、Task、数据快照、代码/算子和审核版本。

报告中的每个关键数值必须链接到 DataFrame Artifact，每个外部事实必须链接到文档页码或数据来源。审核员可以批准、驳回或要求生成新 Plan 版本。已发布报告不可原地修改，只能发布新版本并保留版本关系。

## 13. 持续学习飞轮

### 13.1 Autonomous 模式

后台 Audit Agent 只扫描当前 Workspace 授权范围内的已完成 ResearchRun，并识别：

- Task、Validator 或报告失败；
- 审核员驳回和修改原因；
- 用户重复澄清或纠正；
- 数据来源冲突；
- 人工 override 模型结论；
- 图表或术语与团队规范不一致。

Audit Agent 只能创建 `LearningCandidate`，不能直接修改生产 Context、Prompt、算子或校验器。

### 13.2 Explicit Teach 模式

分析师可以在对话、Plan、结论、证据或图表上点击 Teach，并提交正确方向。系统必须冻结当时的：

- 对话与选中对象；
- ResearchPlan 和 Context 版本；
- 数据快照和检索结果；
- 算子或生成代码版本；
- AnalysisArtifact、ValidationReport 和用户纠正。

### 13.3 Human-audited benchmark 流程

```text
DETECTED
 -> TRIAGED
 -> BENCHMARK_DRAFT
 -> AWAITING_HUMAN
 -> ACCEPTED
 -> CHANGE_PROPOSED
 -> REGRESSION_RUNNING
 -> READY_TO_RELEASE
 -> RELEASED

任一审核态 -> REJECTED
已发布版本 -> ROLLED_BACK
```

每个候选必须先生成一个在当前生产版本上失败的 Benchmark。审核员负责确认输入、预期事实、数值容差、引用、图表要求和可见范围。变更必须通过目标用例和全量回归；管理员才可发布新版本。包含内部资料的用例默认是 Workspace 私有，只有经过管理员脱敏和授权才能提升为全局 Benchmark。

## 14. 错误处理与恢复

- 所有外部调用使用结构化错误码，禁止把异常字符串当成正常 Tool 结果；
- 市场数据适配器最多重试三次，并记录每次来源、时间和错误；
- LLM 编译和代码修复最多两轮；
- Task 必须幂等，重复消息不能产生第二份逻辑结果；
- Worker 崩溃后根据 PostgreSQL 状态和租约恢复，不依赖进程内状态；
- 用户取消后停止未开始 Task，正在运行的沙箱收到终止信号并保留取消审计；
- 缓存损坏时按 Artifact 哈希拒绝读取并重新计算；
- 关键数据不足、权限不足或结果不确定时失败关闭，不生成看似完整的评级；
- 每次失败都返回失败阶段、错误类别、受影响 Task、可重试性和下一步建议。

## 15. 审计与可观测性

每次请求生成 `correlation_id`，贯穿 API、Chat Agent、Plan、Run、Task、Worker、Validator、报告和 Benchmark。结构化日志不得写入 API 密钥或完整敏感文档。

审计事件至少记录：操作者、角色、Workspace、动作、资源、前后版本、时间、原因和关联 ID。应用层不提供审计事件更新或删除接口。

指标至少包括：

- Plan 澄清次数、Plan Gate 失败率；
- Task 编译/执行/校验耗时和失败率；
- 算子路径与生成代码路径比例；
- 缓存命中率；
- 数据缺失率和来源错误率；
- 报告驳回率；
- Autonomous 候选命中率、Teach 采纳率；
- Benchmark 通过率、回归数和版本回滚数；
- 3、10、20 Task 的编译墙钟时间与并行效率。

## 16. API 边界

首版 API 分组如下：

- `/auth/*`：登录回调、会话和当前用户；
- `/workspaces/*`：成员、角色和 ACL；
- `/documents/*`：上传、索引、版本、权限和引用预览；
- `/conversations/*`：Chat Agent 对话、取消和续接；
- `/plans/*`：Plan 版本、校验、确认、批准和拒绝；
- `/runs/*`：创建、状态流、取消、重试和 Artifact；
- `/reports/*`：预览、审核、驳回、发布和版本；
- `/teach/*`：Explicit Teach 提交与跟踪；
- `/learning-candidates/*`：审计候选和人工分流；
- `/benchmarks/*`：用例、运行、比较、审批和发布门；
- `/admin/*`：数据源、Context、算子、校验器和审计管理。

所有资源 API 都必须验证 Workspace 和对象级权限。Streamlit 只调用这些 API，不直接 import 数据层或 Agent 层业务函数。

## 17. 技术栈与运行约束

- Python 3.11 或更高；
- FastAPI 作为业务 API；
- LangGraph 用于 Chat Agent 的持久状态和取消/续接；
- PostgreSQL 16 或更高，pgvector 用于向量检索；
- Redis 7 或更高，用于 Celery broker、并发协调和短期缓存；
- Celery Worker 执行编译、DAG Task 和后台 Audit；
- S3 兼容对象存储保存不可变 Artifact；
- pandas、numpy 承担确定性分析；
- Pydantic 定义所有跨模块契约；
- Alembic 管理数据库迁移；
- Plotly 生成交互式图表；
- OpenTelemetry 关联 API、Agent 和 Worker 链路；
- pytest 承担单元、契约、集成、安全和端到端测试。

部署必须区分 API、Chat Agent、Worker、沙箱执行器和数据存储进程。第一版可使用 Docker Compose 部署到内部环境，但生产密钥不能写入仓库或镜像。

## 18. 测试与 Benchmark

### 18.1 自动化测试

- 单元测试：Plan、Schema、DAG、评分、缓存键和校验器；
- 适配器契约测试：相同逻辑数据在不同来源下得到一致规范 Schema；
- 集成测试：PostgreSQL、Redis、对象存储、任务恢复和报告版本；
- 安全测试：跨 Workspace 文档、缓存、Plan、Artifact 和报告访问必须被拒绝；
- 沙箱测试：网络、文件、进程、动态执行和超资源限制；
- 端到端测试：研究问题到审核报告的完整状态流；
- 失败测试：数据不足、字段冲突、循环 DAG、代码不确定、Worker 崩溃和审核驳回。

### 18.2 行为 Benchmark

Benchmark 用例至少覆盖：

- 研究问题澄清质量；
- Plan 完整性和 Task DAG 正确性；
- 行情、财务、估值和评分数值；
- 文档召回、页码引用和事实支持；
- 生成代码重复执行确定性；
- 3、10、20 Task 并行编译；
- 缓存命中与局部修改；
- 报告数值一致性和风险披露；
- Autonomous 与 Teach 能否生成真实失败用例；
- 新版本是否修复目标用例且不破坏全量回归。

只有在固定模型、固定数据快照、固定并发配置和相同 Plan 下测得的结果，才允许用于性能或确定性声明。

## 19. 当前代码迁移原则

- `finance.py` 的取数逻辑迁移到数据适配器，中文列名在适配器边界内规范化；
- `scoring.py` 的确定性计算保留，但新增数据覆盖和字段语义质量门；
- `rag.py` 的基础流程由带 ACL、页码、混合检索和持久化的文档模块替换；
- `agent.py` 的单 ReAct 循环拆为 Chat Agent 和 Coding Agent 两个运行边界；
- `_CURRENT_STORE` 和其他模块全局业务状态全部移除；
- `app.py` 逐步改为 FastAPI 客户端，迁移期间保留现有演示功能；
- `llm.py` 统一模型配置，禁止 Agent 硬编码不同模型；
- 旧功能在对应新模块通过测试前不删除，避免一次性重写导致无法回归。

## 20. 分阶段子项目

这是一个多子系统升级工程，不能作为单个无边界实现任务执行。后续分别形成实施计划：

1. **基础契约与质量门**：项目结构、Pydantic 领域模型、Plan/Task/Artifact、评分覆盖率和测试基线；
2. **企业后端与隔离**：FastAPI、PostgreSQL、OIDC/RBAC、Workspace、对象存储、审计；
3. **数据与文档平台**：市场适配器、数据快照、ACL 文档、pgvector、引用；
4. **双 Agent 与混合编译**：Chat Agent、Plan Gate、OperatorRegistry、代码沙箱、DAG Worker、缓存；
5. **报告与审核交付**：报告生成、交互图表、审核、发布和 Streamlit API 化；
6. **持续学习与 Benchmark**：Autonomous、Teach、LearningCandidate、回归、版本发布和回滚；
7. **性能与生产验收**：并行度、缓存、故障恢复、安全、负载和指标验证。

每个子项目必须产生可独立运行和验收的软件增量。下一阶段只在前一阶段契约稳定并通过相应测试后开始。

## 21. 总体验收条件

企业级升级完成时必须同时满足：

- Chat Agent 和 Coding Agent 无共享业务状态，且只能通过版本化契约通信；
- 不完整或未批准的 Plan 无法进入执行；
- 标准算子与生成代码 Task 都能按 DAG 执行并通过硬校验；
- 生成代码无法访问网络、宿主文件、环境变量或子进程；
- 相同 Plan、数据快照和环境能产生满足容差的一致 DataFrame；
- 数据不足时系统拒绝给出字母评级；
- 跨 Workspace 访问在 API、检索、缓存和 Artifact 各层均被自动化测试拒绝；
- 每个报告数字、事实和图表都可追溯到版本化 Artifact 或原文页码；
- Worker 中断后任务可恢复，取消和失败均留下审计记录；
- Autonomous 和 Teach 都只能生成待审核候选，不能自动改写生产 Context；
- 新变更必须先复现失败、通过目标 Benchmark 和全量回归，再经管理员发布；
- 所有性能和确定性指标来自项目自己的可复现 Benchmark。

## 22. 设计原则总结

1. LLM 负责澄清、规划、编译建议和解释；确定性系统负责数据、执行、校验和权限。
2. Plan 的质量决定分析上限，因此 Plan 必须比代码生成更早、更严格地被验证。
3. 正确性不能依靠 Agent 记得检查，必须成为不可绕过的 Python 和基础设施约束。
4. 数据、代码、Plan、Context、报告和 Benchmark 都是版本化的一等 Artifact。
5. 用户纠正只有在变成失败 Benchmark 并通过人工审核后，才能沉淀为组织能力。
6. 企业级不是增加更多 Agent，而是建立隔离、可追溯、可恢复、可回归的投研生产流水线。
