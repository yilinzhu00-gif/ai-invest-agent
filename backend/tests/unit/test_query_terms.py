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
