# 离线评测

离线数据集是版本化 JSONL，按公司、时间和文档分组；`holdout` 样例不可用于调参。硬门包括 Schema、数值、引用、ACL、No-answer 和 Tool Policy，任一失败即不可合并。

```bash
uv run python -m backend.app.evals.runner --mode offline --output artifacts/evals/offline.json
```

输出记录数据集版本、模式、样例数和每个硬门的平均分。真实模型评测只允许 nightly/manual 工作流，并必须配置费用上限和人工复核 rubric；当前代码不会隐式发起模型调用。
