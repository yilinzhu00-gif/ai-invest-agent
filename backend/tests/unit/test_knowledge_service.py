import pytest

from backend.app.domain.agent_runs.service import DevelopmentPrincipal
from backend.app.domain.knowledge.service import DocumentUploadError, KnowledgeService
from backend.app.ingestion.parser import DocumentParser


class UnusedRepository:
    class Session:
        async def execute(self, *_: object, **__: object) -> None:
            return None

    session = Session()


@pytest.mark.asyncio
async def test_evidence_library_rejects_office_files_until_original_page_citations_are_supported() -> None:
    service = KnowledgeService(UnusedRepository(), DocumentParser())  # type: ignore[arg-type]

    with pytest.raises(DocumentUploadError, match="invalid_filename"):
        await service.upload(
            principal=DevelopmentPrincipal("analyst-1", "workspace-a"),
            filename="重大资产重组报告书.docx",
            content=b"not parsed",
            symbol="600519",
            document_type="announcement",
            source_url=None,
        )
