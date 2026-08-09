# ADR：阶段四预研证据工具

- 日期：2026-08-09
- 状态：已接受
- 决策范围：离线预研代码，不代表阶段四工作包获准上线。

## 决策

在正式阶段四门禁仍为 NO-GO 的情况下，允许合并四类纯离线证据工具：受控 Agent 三臂对照、后端基准汇总、训练候选治理和平台容量准备度判断。这些工具只消费外部实验产生的观察值或人工批准候选，不调用模型、不连接数据库、不创建 GPU/Kubernetes 资源，也不修改生产 Flow、Model Router、Tool Policy 或部署路径。

结构化结果中的 `GO` 或 `EVIDENCE_READY` 仅表示标记为 `REAL_ATTESTED` 的输入证据满足当前预注册规则。每份真实证据必须记录来源引用、产物 SHA-256、采集时间和证明人；`SYNTHETIC`、`UNVERIFIED`、Mock 或 fixture 最高只能得到 `INSUFFICIENT_EVIDENCE`。该来源契约用于防止误用，不等同于系统独立核验，也不能绕过阶段三生产门禁、8 周真实数据、人工审批、负责人、预算或回滚要求。

## 模块边界

- `backend.app.agents.experiment`：三臂必须属于同一注册实验，并逐 case 使用相同 ID 与输入 SHA-256；同 Token 组与专门 Agent 还必须逐 case 使用相同模型和 Token 预算。默认至少 100 个 case，专门 Agent 相对同 Token 组硬门至少提高 5 个百分点并满足成本、延迟预算才返回 `GO`。
- `backend.app.benchmarks.backends`：只比较同模块、同数据集版本与 SHA-256、同 case ID 与输入 SHA-256 且延迟为正数的后端；质量门槛用十进制定点语义判断，舍入只用于展示。结果最高为 `EVIDENCE_READY`，不自动切换 OCR、Embedding、Rerank 或生成模型。
- `backend.app.training.export`：审批、许可证、授权或敏感信息任一失败即 `NO_GO`；样本保留工作区、源运行、源文档、内容哈希和审批血缘，同一源运行或源文档不得跨 train/holdout，重复内容不得导出。检测覆盖输入输出和所有会导出的文本元数据，并显式识别 PII、AWS/GitHub/Slack/Google/GitLab 凭证、私钥和密码赋值。默认不足 300 个 train 或 50--100 个 holdout 时不产生可用 examples 或 dataset hash。
- `backend.app.platform.capacity`：不足 8 周为 `INSUFFICIENT_EVIDENCE`；每个真实技术触发、预算批准和回滚演练都必须有 SHA-256 证据引用；缺少触发、owner、预算或回滚演练时为 `NO_GO`，且绝不生成基础设施配置。

## 回滚

这些模块尚无生产消费者。回滚只需停止生成或读取预研报告并回退对应代码提交，不涉及数据库迁移、模型权重、索引或云资源。未来任何生产接入必须单独提交 ADR、实现计划、功能开关和回滚验证。
