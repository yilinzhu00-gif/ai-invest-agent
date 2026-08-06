# P2-06 pgvector 混合 RAG 与 ACL 引用

> 状态：执行中。检索先授权过滤，后评分；离线评测不调用 embedding 或 rerank API。

## 目标

用 PostgreSQL pgvector/全文索引保存可撤销、可引用的知识块。稠密和关键词独立召回，RRF 融合，Rerank 仅重排已授权候选。所有 `EvidenceItem` 保留 document/version/page/block/table/cell/bbox 和阶段分数。

## 顺序

1. 测试 ACL=0 泄露、撤销即不可召回、RRF 与精确单元格引用。
2. 实现内存可替换 repository/retrieval/citation/lifecycle 边界并接正式 Tool schema。
3. 切换 Compose 到 pgvector，增加 extension/GIN/vector 索引迁移；隔离数据库验证。
4. 增加 RAG JSONL 评测 CLI，报告 Recall@K、MRR、Citation Accuracy 和 No-answer。

## 回滚

索引 profile 版本化；指标下降时切换到前一 profile，旧 embedding 不删除。
