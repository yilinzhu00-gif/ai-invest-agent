# ADR：阶段四进入门禁审计

- 日期：2026-08-09
- 状态：已决定（NO-GO）
- 范围：P4-01 更多 Agent、P4-02 GPU/本地模型、P4-03 Fine-tuning/LoRA、P4-04 Kubernetes/服务拆分/数据库扩容。

## 决策

不实施任何阶段四工作包，也不创建无消费者的 Agent、GPU、训练或 Kubernetes 框架。阶段四的共同前置条件未满足：阶段三仍有未验证或未实现的生产门禁，且仓库中没有连续 8 周真实流量、成本、固定评测与人工审核数据。

本 ADR 只记录审计结论和重新评估条件；它不把本地测试、Compose 静态检查或脚手架视为生产验证。

## 已实际验证的本地证据

| 命令 | 结果 | 边界 |
| --- | --- | --- |
| `uv --cache-dir /private/tmp/p4-uv-cache run pytest -q` | 退出码 0；103 passed、10 skipped | 离线测试；跳过项和外部系统不等同于运行态验证。 |
| `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend test -- --run && npm --prefix frontend run build` | 退出码 0；17 tests passed，构建完成 | 仅本地前端质量门。 |
| `docker compose --env-file deploy/env/development.example -f deploy/compose.base.yml -f deploy/compose.dev.yml config -q` | 退出码 0 | 仅 Compose 合并校验，未启动服务。 |
| `DRILL_ENV=test ./scripts/backup-restore-drill.sh` | 退出码 0；PostgreSQL 行数 1，备份与恢复 SHA-256 一致 | 一次本机隔离容器演练；不是生产 RPO/RTO 演练。 |
| `python -m backend.app.evals.runner --mode offline --dataset evals/agent/research_cases.jsonl --output /private/tmp/p4-root-agent-eval.json` | 退出码 0；1 个 case，所有本地 gate 为 1.0 | 仅一个 fixture，不能代表真实 Agent 质量或 A/B。 |
| `python -m backend.app.agents.benchmark --runtime langgraph --dataset evals/agent/baseline_cases.jsonl` | 退出码 0；1 case、cost_microusd=0 | 不是同 Token 的 Control/Treatment。 |
| `python -m backend.app.domain.knowledge.evaluate --dataset evals/rag/queries.jsonl` | 退出码 0；2 cases | 样本量不足以支持阶段四决策。 |

`./scripts/run-k6.sh` 曾以默认 `BASE_URL=http://127.0.0.1:8000` 实际运行，但该地址没有可用 API，运行输出为 `dial tcp 127.0.0.1:8000: connect: operation not permitted`，且没有生成 `reports/k6/summary.json`；它不能作为 Mock 压测、真实模型测试或 30 分钟 soak 证据。

## 阶段三退出门禁

| 门禁 | 状态 | 缺口 |
| --- | --- | --- |
| OIDC/JWT、RBAC、ACL、RLS | 未验证 | 代码和离线测试存在，但没有真实 OIDC/JWKS、PostgreSQL RLS、SSE/下载/后台任务授权快照的集成证据。 |
| Prompt/PII/RESTRICTED/文件安全 | 未完成 | 本地规则和测试存在；没有第三方外发、日志扫描的运行证据，且文件管线没有压缩炸弹、页数限制、ClamAV 与隔离运行态验证。 |
| Redis/Celery、幂等、取消、背压 | 未完成 | 路由配置存在，但缺少四类 Worker 的运行生命周期、Redis/PostgreSQL 实测和队列背压证据。 |
| 限流、并发、Token、费用预算 | 未完成 | 当前限流为进程内实现，未证明用户/workspace/provider 的 Redis 配额、并发和费用执行。 |
| 统一 Trace、日志、指标、告警 | 未完成 | OTel/Prometheus/Grafana 配置存在，但没有跨 API、SSE、Worker、DB、Tool、模型与 RAG 的统一运行 Trace 或历史指标。 |
| CI/CD、安全扫描、staging、人工 production 与回滚 | 未完成 | 未见部署/回滚工作流、SBOM、CodeQL、Trivy、secret scan、staging smoke 或生产审批和 digest 回滚记录。 |
| 负载与恢复 | 未完成 | 本机隔离恢复脚本已运行一次；Mock/真实模型/30 分钟 soak 分开报告、生产级 RPO/RTO 仍缺失。 |

阶段三不是整体通过状态，因此阶段四被阻断。

## 阶段四逐包结论

| 工作包 | 决策 | 不实施原因 | 重新评估条件 |
| --- | --- | --- | --- |
| P4-01 更多 Agent | NO-GO | 没有至少 100 个 holdout 的连续失败模式；没有独立 schema/tool/责任边界；没有相同模型、输入和 Token 预算的三组对照，也没有硬门 +5pp 的收益。 | 完成 P3 后，积累 8 周真实数据。以下三项至少满足两项才可立项：100+ holdout 持续低于门槛；独立 input/output schema、Tool 白名单和责任边界；相同输入/模型/Token 口径的 A/B 硬门提高至少 5 个百分点且延迟、单 Run 成本在批准预算内。预注册单 Agent、同 Token 单 Agent、专门 Agent 三组实验，并记录质量、成本、延迟和新失败类型。 |
| P4-02 GPU/本地模型 | INSUFFICIENT-EVIDENCE | OCR、Embedding、Rerank、生成均无连续 p95、profiling、三个月云成本/TCO、合规本地处理要求或配额瓶颈的真实证据。 | 每个模块独立评估。满足任一条件才可立项：OCR 连续 2 周文档 p95 超过 120 秒且 profiler 归因 OCR；Embedding/Rerank 连续 3 个月云成本高于本地 TCO 1.5 倍；RESTRICTED 数据明确要求本地处理；或 Provider 配额限制吞吐且本地方案在固定评测达到质量门。所有路径均需质量、p50/p95、吞吐、失败率、成本和回滚对照。 |
| P4-03 Fine-tuning/LoRA | NO-GO | 没有 TrainingCandidate、约 300 个经人工批准训练样本、50--100 个隔离 holdout、样本级授权/许可证/血缘、group split、稳定基座许可或 Prompt/RAG/Tool 未达标的对照。 | 建立人工审核和批准数据集；导出 fail-closed 的 PII/Secret/ACL/license/group-leakage 门；完成基座 Prompt 与 LoRA/QLoRA 的 holdout、shadow 和安全对照。 |
| P4-04 Kubernetes/服务拆分/数据库扩容 | NO-GO | 无已批准 SLA/RTO、事故、容量违约、反复由发布边界导致的事故、数据库优化后仍不足、平台负责人或预算的真实证据。 | 先取得 8 周容量、事故和发布记录，并完成无状态横扩、索引/缓存/连接池/PgBouncer 对照；仅在现有 HA 或扩缩仍违反 SLO、发布边界反复造成事故，或数据库优化后仍不足，且 owner、预算、回滚演练具备时，拆一个资源瓶颈模块。 |

## 必须采集的可审计基线

从阶段三生产验证完成之日起，连续至少 8 周保留脱敏、可追溯的日/周聚合。每条数据应关联 run/trace 与版本，但不得将 Prompt、正文、PII 或 Secret 写入指标标签：

- API、SSE、Agent、RAG、OCR、Embedding、Rerank 的吞吐、失败率、p50/p95/p99；
- queued_at、started_at、finished_at 以及队列等待、重试、429、缓存 hit/miss、CPU/内存、数据库连接/慢查询；
- 每 Run 的 Token、按价格版本计算的成本、模型/Provider 配额与真实账单对账；
- 固定 holdout 的版本、样本数、质量门、失败簇和 Control/Treatment 原始结果；
- 人工审核的批准/驳回、rubric、reason code、审阅者、时间、权限、数据来源、许可证和 split group；
- 已批准的 SLA/SLO、RTO/RPO、事故复盘、工作包 owner、预算和经过演练的回滚路径。

重新评估时必须先重跑阶段三门禁，再审计上述数据；任何缺项维持 NO-GO 或 INSUFFICIENT-EVIDENCE，不以脚手架、Mock 或主观判断补齐。
