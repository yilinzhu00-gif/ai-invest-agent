from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from backend.app.api.v1.documents import get_knowledge_service
from backend.app.core.config import Settings
from backend.app.domain.knowledge.schemas import (
    DocumentResponse,
    EvidenceSearchResult,
    TransactionFactEvidence,
    TransactionFactRow,
    TransactionFactsResponse,
)
from backend.app.main import create_app
from backend.app.tools.event_study import (
    BeforeAfterChange,
    Benchmark,
    EventMarketDate,
    MarketReactionResponse,
    VolumeVolatilityChange,
    WindowReturn,
)

DEMO_HEADERS = {
    "X-Development-Principal-ID": "analyst-1",
    "X-Development-Workspace-ID": "workspace-a",
}
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000021")


class FakeKnowledgeService:
    def __init__(self) -> None:
        self.uploads: list[dict[str, object]] = []

    async def upload(self, **kwargs: object) -> DocumentResponse:
        self.uploads.append(kwargs)
        return DocumentResponse(
            id=DOCUMENT_ID,
            filename=str(kwargs["filename"]),
            symbol=str(kwargs["symbol"]),
            document_type="announcement",
            source_url=str(kwargs["source_url"]),
            version=1,
            status="ready",
            page_count=12,
            parsed_block_count=24,
            created_at=datetime.now(UTC),
        )

    async def search(self, **_: object) -> list[EvidenceSearchResult]:
        return [
            EvidenceSearchResult(
                evidence_id=f"document:{DOCUMENT_ID}:block:7",
                document_id=DOCUMENT_ID,
                document_version=1,
                filename="重大资产重组报告书.pdf",
                source_url="https://example.com/announcement.pdf",
                page_number=8,
                block_id="7",
                text="本次交易对价为 10 亿元。",
                parser="native",
                confidence=1,
                bbox=None,
            )
        ]

    async def list_documents(self, **_: object) -> list[DocumentResponse]:
        return [
            DocumentResponse(
                id=DOCUMENT_ID,
                filename="重大资产重组报告书.pdf",
                symbol="600519",
                document_type="announcement",
                source_url="https://example.com/announcement.pdf",
                version=1,
                status="ready",
                page_count=12,
                parsed_block_count=24,
            )
        ]

    async def extract_transaction_facts(self, **_: object) -> TransactionFactsResponse:
        return TransactionFactsResponse(
            document_id=DOCUMENT_ID,
            filename="重大资产重组报告书.pdf",
            document_version=1,
            rows=[
                TransactionFactRow(
                    field="交易对价",
                    value="已在公告原文中披露",
                    evidence=[
                        TransactionFactEvidence(
                            page_number=8, block_id="7", text="本次交易对价为 10 亿元。"
                        )
                    ],
                ),
                TransactionFactRow(field="资金来源", value="公告未披露", evidence=[]),
            ],
            boundary="仅展示公告原文和页码。",
        )

    async def get_ready_announcement(self, **_: object) -> DocumentResponse:
        return DocumentResponse(
            id=DOCUMENT_ID,
            filename="重大资产重组报告书.pdf",
            symbol="600519",
            document_type="announcement",
            source_url="https://example.com/announcement.pdf",
            version=1,
            status="ready",
            page_count=12,
            parsed_block_count=24,
        )


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(max_request_body_bytes=256, document_upload_max_bytes=1024))
    fake = FakeKnowledgeService()
    app.dependency_overrides[get_knowledge_service] = lambda: fake
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_upload_accepts_a_document_larger_than_the_normal_json_request_limit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/documents",
        params={
            "filename": "重大资产重组报告书.md",
            "symbol": "600519",
            "document_type": "announcement",
            "source_url": "https://example.com/announcement.pdf",
        },
        content=b"x" * 512,
        headers=DEMO_HEADERS | {"content-type": "application/octet-stream"},
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": str(DOCUMENT_ID),
        "filename": "重大资产重组报告书.md",
        "symbol": "600519",
        "document_type": "announcement",
        "source_url": "https://example.com/announcement.pdf",
        "version": 1,
        "status": "ready",
        "page_count": 12,
        "parsed_block_count": 24,
        "created_at": response.json()["created_at"],
    }


def test_search_returns_page_and_document_version_with_each_evidence_block(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "交易对价", "document_id": str(DOCUMENT_ID)},
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["filename"] == "重大资产重组报告书.pdf"
    assert result["document_version"] == 1
    assert result["page_number"] == 8
    assert result["text"] == "本次交易对价为 10 亿元。"


def test_list_documents_exposes_only_the_workspace_scoped_selection_contract(client: TestClient) -> None:
    response = client.get("/api/v1/documents", headers=DEMO_HEADERS)

    assert response.status_code == 200
    assert response.json()[0]["id"] == str(DOCUMENT_ID)
    assert response.json()[0]["status"] == "ready"


def test_transaction_facts_return_verbatim_text_with_a_page_or_not_disclosed(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/documents/{DOCUMENT_ID}/transaction-facts", headers=DEMO_HEADERS
    )

    assert response.status_code == 200
    rows = {row["field"]: row for row in response.json()["rows"]}
    assert rows["交易对价"]["evidence"] == [
        {"page_number": 8, "block_id": "7", "text": "本次交易对价为 10 亿元。"}
    ]
    assert rows["资金来源"] == {"field": "资金来源", "value": "公告未披露", "evidence": []}


def test_market_reaction_is_bound_to_the_selected_announcement(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_reaction(**_: object) -> MarketReactionResponse:
        return MarketReactionResponse(
            symbol="600519",
            announcement_date="2025-01-26",
            event_date="2025-01-27",
            event_window=[-20, 20],
            benchmark_indices=[Benchmark(name="沪深300", symbol="000300", source="AkShare")],
            formula="固定公式",
            before_after_change=BeforeAfterChange(
                before_date="2025-01-24", event_date="2025-01-27", after_date="2025-01-28",
                before_to_event_return_percent=1, event_to_after_return_percent=2,
            ),
            window_result=WindowReturn(
                start_offset=-20, end_offset=20, start_date="2024-12-20", end_date="2025-02-20",
                stock_start_close=10, stock_end_close=11, csi_300_start_close=1000, csi_300_end_close=1010,
                industry_start_close=2000, industry_end_close=2010, stock_return_percent=10,
                csi_300_return_percent=1, industry_return_percent=0.5,
                excess_vs_csi_300_percentage_points=9, excess_vs_industry_percentage_points=9.5,
            ),
            volume_volatility_change=VolumeVolatilityChange(
                pre_period="[-20, -1]", post_period="[0, +20]", pre_average_volume=100,
                post_average_volume=120, volume_change_percent=20, pre_daily_volatility_percent=1,
                post_daily_volatility_percent=2, volatility_change_percentage_points=1,
            ),
            market_dates=[EventMarketDate(
                event_offset=0, market_date="2025-01-27", stock_close=10.5, stock_volume=110,
                csi_300_close=1005, industry_index_close=2005,
            )],
            missing_trading_dates=[],
            missing_trading_dates_definition="定义",
            source="AkShare",
            boundary="不作因果归因。",
        )

    monkeypatch.setattr("backend.app.api.v1.market_reactions.fetch_market_reaction", fake_reaction)
    response = client.post(
        f"/api/v1/documents/{DOCUMENT_ID}/market-reaction",
        json={
            "announcement_date": "2025-01-26",
            "industry_index_symbol": "801010",
            "industry_index_name": "申万行业",
        },
        headers=DEMO_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["event_window"] == [-20, 20]
    assert response.json()["window_result"]["excess_vs_csi_300_percentage_points"] == 9


def test_non_document_requests_still_use_the_small_request_limit(client: TestClient) -> None:
    response = client.post(
        "/api/v1/knowledge/search",
        content=b"x" * 512,
        headers=DEMO_HEADERS | {"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_body_too_large"
