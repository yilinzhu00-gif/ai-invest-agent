# 阶段四预研代码设计

## 目标

在不能上线、没有真实 GPU、没有批准训练集、没有生产容量数据的前提下，建立可离线运行的阶段四证据工具。工具只回答“现有证据是否足够”和“候选是否达到预注册门槛”，不接入生产执行路径，也不把合成测试数据当作阶段四触发证据。

## 范围

### P4-01 受控 Agent 对照

新增只读 `AgentCapability` 契约和三臂实验评估器。三臂固定为当前基线、同 Token 基线和专门 Agent；评估器要求三臂属于同一注册实验并逐 case 使用相同 ID 与输入 SHA-256，同 Token 基线与专门 Agent 还必须使用相同模型和 Token 预算。默认至少 100 个 case，并以同 Token 基线为对照计算硬门提升、p95 延迟和平均成本。它只读取已产生的观察值，不调用模型，不修改 `ControlledResearchFlow`。

### P4-02 后端基准证据

新增 OCR、Embedding、Rerank、Generation 共用的后端描述和观察值契约。control/candidate 必须使用相同数据集版本与 SHA-256，以及相同 case ID 与输入 SHA-256。纯函数汇总质量、成功率、p50/p95、串行吞吐、平均成本和失败类型，并使用十进制定点语义判断质量门槛。它不创建 GPU 容器，不下载模型，不修改 Model Router。

### P4-03 训练数据治理

新增 `TrainingCandidate`、审批状态、许可证、工作区/源运行/源文档/内容哈希血缘和 split group 契约。导出器只接受显式批准、允许训练、权限明确且不含可识别 PII 或已登记常见 Secret 的候选；扫描所有会导出的文本字段，拒绝重复内容，并禁止同一源运行或源文档跨 train/holdout。通过后按 group 分配数据集、计算稳定 dataset hash，并以默认 300 个 train、50--100 个 holdout 为准备门禁。它不训练模型，不持久化输入数据，不生成模型权重。

### P4-04 平台容量决策

新增纯离线容量证据评估器。只有至少 8 周观察、至少一个有 SHA-256 引用的真实技术触发、平台负责人，以及有 SHA-256 引用的预算批准和回滚演练同时具备时，才返回 `EVIDENCE_READY`。不创建 Kubernetes、微服务、Kafka、分片或云资源配置。

## 数据流

所有模块都采用 `输入观察/候选 -> 严格校验 -> 纯函数汇总 -> 结构化决策`。观察证据统一记录种类、来源引用、产物 SHA-256、采集时间和证明人；只有 `REAL_ATTESTED` 可以到达正向决策，`SYNTHETIC` 与 `UNVERIFIED` 固定停在 `INSUFFICIENT_EVIDENCE`。该契约不做外部签名验证。代码不会自动启用任何能力，生产系统、外部 Provider、GPU、云账户、数据库和用户数据都不是运行依赖。

## 安全与失败处理

- Pydantic 模型使用 `extra="forbid"`，拒绝未知字段。
- Agent capability 固定只读、禁止委派、最大调用 1。
- 对照实验 ID、case ID/输入摘要、同 Token 模型或预算不一致时拒绝比较，Token 用量不得超过预注册预算。
- 后端数据集版本/摘要、模块或 case ID/输入摘要不一致时拒绝比较。
- 门槛比较使用未舍入值，舍入值只用于展示。
- 训练导出对审批、许可证、权限、已登记 PII/Secret、重复内容、源运行和 split group 采用 fail-closed；正则清单不等同于通用 Secret scanner。
- RESTRICTED 候选只有显式 `training_authorized=True` 才可进入本地训练导出证据。
- 平台技术触发缺少对应证据引用时采用 fail-closed。
- 工具本身不写日志或持久化输入；训练报告仅在候选通过治理门后于内存中返回获批文本与血缘，检测到的 PII/Secret 不进入可用导出。

## 验证

每个新模块先写失败测试，再实现最小代码。定向测试覆盖不足样本、case 不匹配、预算超限、质量下降、敏感数据拒绝、group split、稳定 hash 和平台前置条件。最终运行 Ruff、mypy、后端全量测试、前端既有质量门、Compose config 和 `git diff --check`。

## 明确不做

- 不新增真实 Agent 节点或 Prompt；
- 不生成 100 条伪造 holdout 作为项目证据；
- 不创建 GPU Worker/Compose overlay；
- 不训练 LoRA/QLoRA，不生成权重；
- 不创建 Kubernetes manifests 或拆服务；
- 不修改 API、数据库、生产 Flow、Tool Policy、Model Router 或部署工作流。
