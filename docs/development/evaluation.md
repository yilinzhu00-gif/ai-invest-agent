# 离线评测

离线数据集是版本化 JSONL，按公司、时间和文档分组；`holdout` 样例不可用于调参。硬门包括 Schema、数值、引用、ACL、No-answer 和 Tool Policy，任一失败即不可合并。

```bash
uv run python -m backend.app.evals.runner --mode offline --output artifacts/evals/offline.json
```

输出记录数据集版本、模式、样例数和每个硬门的平均分。真实模型评测只允许 nightly/manual 工作流，并必须配置费用上限和人工复核 rubric；当前代码不会隐式发起模型调用。

## 阶段四预研证据工具

受控 Agent 对照读取三臂离线观察值。输入必须属于同一注册实验并逐 case 使用相同 ID 与输入 SHA-256；同 Token 与专门 Agent 还必须使用相同模型和 Token 预算，默认至少 100 个 case。命令只输出证据判断，不调用模型或修改生产 Flow：

```bash
uv run python -m backend.app.agents.experiment --input observations.jsonl
```

OCR、Embedding、Rerank 或 Generation 的 control/candidate 结果可以使用统一后端证据模型比较。两侧必须属于相同模块，并使用相同数据集版本/摘要和 case ID/输入摘要：

```bash
uv run python -m backend.app.benchmarks.backends \
  --control control-observations.jsonl \
  --candidate candidate-observations.jsonl
```

训练导出和平台扩容判断目前只通过 Python API 使用。`prepare_training_export()` 会扫描所有导出文本字段，拒绝已登记敏感信息、重复内容以及跨 split 的同源运行或文档，默认不足 300 个 train 或 50--100 个 holdout 时不返回可用数据集；内置正则不是通用 Secret scanner。`evaluate_platform_scale()` 不足 8 周，或缺少带哈希引用的技术触发、负责人、预算批准、回滚演练时不会返回 `EVIDENCE_READY`。

观察值必须携带来源引用、产物 SHA-256、采集时间和证明人。以上命令的合成 fixture、Mock 或本地输出必须标记为 `SYNTHETIC` 或 `UNVERIFIED`，最高只会得到 `INSUFFICIENT_EVIDENCE`；即使输入标记为 `REAL_ATTESTED`，本地契约也不负责独立验证证明人的身份。真实立项仍需满足阶段三门禁、连续运行数据、人工审批、许可证与外部环境验证。
