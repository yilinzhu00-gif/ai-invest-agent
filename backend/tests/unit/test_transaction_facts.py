from types import SimpleNamespace

from backend.app.domain.knowledge.transaction_facts import NOT_DISCLOSED, extract_transaction_facts


def block(block_id: int, page: int, text: str) -> SimpleNamespace:
    return SimpleNamespace(id=block_id, page_number=page, text=text)


def test_transaction_facts_preserve_source_text_and_page_without_inferring_missing_values() -> None:
    rows = extract_transaction_facts(
        [
            block(7, 8, "本次交易对价为10亿元，交易对方为甲公司。"),
            block(8, 9, "交易完成后预计将增加营业收入，但不会对经营现金流产生重大不利影响。"),
            block(9, 10, "2025年度营业收入为2亿元。"),
        ]
    )
    by_field = {row.field: row for row in rows}

    assert by_field["交易对价"].evidence[0].text == "本次交易对价为10亿元，交易对方为甲公司。"
    assert by_field["交易对价"].evidence[0].page_number == 8
    assert by_field["交易对手"].evidence[0].page_number == 8
    assert by_field["对营收的预计影响"].evidence[0].page_number == 9
    assert by_field["对现金流的预计影响"].evidence[0].page_number == 9
    assert by_field["对利润的预计影响"].value == NOT_DISCLOSED
    assert by_field["对利润的预计影响"].evidence == []


def test_transaction_facts_return_every_fixed_field_as_not_disclosed_when_no_direct_text_exists() -> None:
    rows = extract_transaction_facts([block(1, 1, "本公告仅说明公司日常经营情况。")])

    assert len(rows) == 14
    assert all(row.value == NOT_DISCLOSED and row.evidence == [] for row in rows)
