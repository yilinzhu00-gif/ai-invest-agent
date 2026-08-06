# Streamlit 退役门禁

Streamlit 仅保留为迁移回归入口，禁止新增业务功能。Next.js/FastAPI 必须连续两个发布周期无 P0 回归，并为下列五项功能提供等价证据，才可单独创建退役 PR：

| 功能 | 新路径 | 当前证据 |
| --- | --- | --- |
| 行情与指标 | FastAPI Tool Registry | P2-03 Schema/权限测试 |
| 量化评分 | `/api/v1/scoring` | API 与评分测试 |
| 研究问答 | Agent Run + CrewAI Flow | P2-01/P2-04 测试 |
| 文档检索 | pgvector Hybrid RAG | P2-06 ACL/RAG 评测 |
| 投研展示 | Next.js `/scoring`、`/agent-runs` | 前端单测与构建 |

没有以上证据或发布周期记录时，不删除 `legacy/`。CI 脚本拒绝普通提交修改 `legacy/`，以避免在迁移期继续扩展 Streamlit。
