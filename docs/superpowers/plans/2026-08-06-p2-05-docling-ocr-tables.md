# P2-05 Docling、选择性 OCR 与复杂表格

> 状态：执行中。Docling 仅作为 `document-worker` extra；API 进程不会主动导入它。

## 目标与边界

为 PDF、DOCX、XLSX、PPTX、Markdown、HTML、CSV 和图片建立可重跑的版本化解析结果。先做文件安全检查；原生文本优先，低文本密度才 OCR。VLM 不启用。表格保存单元格、bbox、单位、原始页和检索文本；相邻页且置信度达到 0.90 才自动合并，其他候选显式进入人工复核。

## 实施顺序

1. 写失败测试，覆盖原生页不 OCR、扫描页 OCR、表格无损字段和低置信跨页复核。
2. 增加纯 Python 的 schema、分类、OCR adapter 接口、表格/跨页规则与解析器；测试均以注入 extractor/OCR 离线执行。
3. 将 Docling 锁入独立 optional extra，并在 CLI 中延迟导入；未安装 extra 时给出明确错误。
4. 新增 `documents`、`document_blocks`、`table_blocks` 版本化数据库模型和迁移，解析结果不会原地覆盖旧版本。
5. 使用小型离线 fixture 验证安全边界和 CLI 路径；真实 OCR 准确率/CER 由后续有标注扫描语料门禁维护。

## 验收命令

```bash
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest backend/tests/integration/test_document_ingestion.py -q
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run python -m backend.app.ingestion.cli backend/tests/fixtures/documents/native.md
UV_CACHE_DIR=/private/tmp/investment-agent-uv-cache uv run pytest -q
```

## 回滚

停止新增解析任务并将 worker image 回退；Document 以 `parser_version` 创建新版本，旧块和原表不原地修改。
