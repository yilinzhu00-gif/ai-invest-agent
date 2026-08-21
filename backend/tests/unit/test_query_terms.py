from backend.app.domain.knowledge.query_terms import retrieval_query_terms


def test_chinese_factual_question_keeps_the_retrievable_evidence_phrase() -> None:
    terms = retrieval_query_terms("交易对价是多少")

    assert terms[0] == "交易对价"
    assert "对价" in terms


def test_space_separated_terms_remain_available_for_keyword_retrieval() -> None:
    assert retrieval_query_terms("收购 对价 是什么") == ["收购", "对价"]


def test_forecast_question_expands_to_a_retrievable_financial_term() -> None:
    assert retrieval_query_terms("研报对 2025年净利润的预测是多少") == [
        "2025年净利润的预测",
        "净利润",
        "预测",
    ]


def test_spaces_inside_a_chinese_forecast_question_do_not_hide_financial_terms() -> None:
    terms = retrieval_query_terms("研报对 2025 年净利润的预测是多少")

    assert "净利润" in terms
    assert "预测" in terms


def test_natural_language_question_extracts_a_non_financial_factual_fragment() -> None:
    terms = retrieval_query_terms("星网锐捷2026年半年报中核心竞争力是什么")

    assert terms[0] == "星网锐捷2026年半年报中核心竞争力"
    assert "核心竞争力" in terms


def test_question_scaffolding_does_not_become_the_only_retrieval_term() -> None:
    terms = retrieval_query_terms("该公告披露的重大资产重组进展如何")

    assert "重大资产重组进展" in terms
