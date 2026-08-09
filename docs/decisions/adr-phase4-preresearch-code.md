# ADR：阶段四预研证据工具

- 日期：2026-08-09
- 状态：已接受
- 决策范围：离线预研代码，不代表阶段四工作包获准上线。

## 决策

在正式阶段四门禁仍为 NO-GO 的情况下，允许合并四类纯离线证据工具：受控 Agent 三臂对照、后端基准汇总、训练候选治理和平台容量准备度判断。这些工具只消费外部实验产生的观察值或人工批准候选，不调用模型、不连接数据库、不创建 GPU/Kubernetes 资源，也不修改生产 Flow、Model Router、Tool Policy 或部署路径。

结构化结果中的 `GO` 或 `EVIDENCE_READY` 仅表示输入证据满足当前预注册规则。它不能绕过阶段三生产门禁、8 周真实数据、人工审批、负责人、预算或回滚要求。

## 模块边界

- `backend.app.agents.experiment`：三臂 case 集必须完全一致，默认至少 100 个 case；专门 Agent 相对同 Token 组硬门至少提高 5 个百分点并满足成本、延迟预算才返回 `GO`。
- `backend.app.benchmarks.backends`：只比较同模块、同数据集、同 case 集的后端；结果最高为 `EVIDENCE_READY`，不自动切换 OCR、Embedding、Rerank 或生成模型。
- `backend.app.training.export`：审批、许可证、授权或敏感信息任一失败即 `NO_GO`；默认不足 300 个 train 或 50--100 个 holdout 时不产生可用 examples 或 dataset hash。
- `backend.app.platform.capacity`：不足 8 周为 `INSUFFICIENT_EVIDENCE`；没有真实技术触发、owner、预算或回滚演练时为 `NO_GO`，且绝不生成基础设施配置。

## 回滚

这些模块尚无生产消费者。回滚只需停止生成或读取预研报告并回退对应代码提交，不涉及数据库迁移、模型权重、索引或云资源。未来任何生产接入必须单独提交 ADR、实现计划、功能开关和回滚验证。
