# 阶段四预研代码设计

## 目标

在不能上线、没有真实 GPU、没有批准训练集、没有生产容量数据的前提下，建立可离线运行的阶段四证据工具。工具只回答“现有证据是否足够”和“候选是否达到预注册门槛”，不接入生产执行路径，也不把合成测试数据当作阶段四触发证据。

## 范围

### P4-01 受控 Agent 对照

新增只读 `AgentCapability` 契约和三臂实验评估器。三臂固定为当前基线、同 Token 基线和专门 Agent；评估器要求三臂使用相同 case 集，默认至少 100 个 case，并以同 Token 基线为对照计算硬门提升、p95 延迟和平均成本。它只读取已产生的观察值，不调用模型，不修改 `ControlledResearchFlow`。

### P4-02 后端基准证据

新增 OCR、Embedding、Rerank、Generation 共用的后端描述和观察值契约。纯函数汇总质量、成功率、p50/p95、串行吞吐、平均成本和失败类型，并比较 control/candidate 是否具备进一步评估条件。它不创建 GPU 容器，不下载模型，不修改 Model Router。

### P4-03 训练数据治理

新增 `TrainingCandidate`、审批状态、许可证、血缘和 split group 契约。导出器只接受显式批准、允许训练、权限明确且不含可识别敏感文本的候选；按 group 分配 train/holdout，计算稳定 dataset hash，并以默认 300 个 train、50--100 个 holdout 为准备门禁。它不训练模型，不保存真实训练数据，不生成模型权重。

### P4-04 平台容量决策

新增纯离线容量证据评估器。只有至少 8 周观察、至少一个真实技术触发、平台负责人、预算和回滚演练同时具备时，才返回 `EVIDENCE_READY`。不创建 Kubernetes、微服务、Kafka、分片或云资源配置。

## 数据流

所有模块都采用 `输入观察/候选 -> 严格校验 -> 纯函数汇总 -> 结构化决策`。默认决策为 `INSUFFICIENT_EVIDENCE` 或 `NO_GO`；代码不会自动启用任何能力。生产系统、外部 Provider、GPU、云账户、数据库和用户数据都不是依赖。

## 安全与失败处理

- Pydantic 模型使用 `extra="forbid"`，拒绝未知字段。
- Agent capability 固定只读、禁止委派、最大调用 1。
- 对照 case 集不一致时拒绝比较。
- 后端数据集、模块或 case 集不一致时拒绝比较。
- 训练导出对审批、许可证、权限、PII/Secret 和 split group 采用 fail-closed。
- RESTRICTED 候选只有显式 `training_authorized=True` 才可进入本地训练导出证据。
- 不记录 Prompt、文档正文、真实 Secret 或生产标识。

## 验证

每个新模块先写失败测试，再实现最小代码。定向测试覆盖不足样本、case 不匹配、预算超限、质量下降、敏感数据拒绝、group split、稳定 hash 和平台前置条件。最终运行 Ruff、mypy、后端全量测试、前端既有质量门、Compose config 和 `git diff --check`。

## 明确不做

- 不新增真实 Agent 节点或 Prompt；
- 不生成 100 条伪造 holdout 作为项目证据；
- 不创建 GPU Worker/Compose overlay；
- 不训练 LoRA/QLoRA，不生成权重；
- 不创建 Kubernetes manifests 或拆服务；
- 不修改 API、数据库、生产 Flow、Tool Policy、Model Router 或部署工作流。
