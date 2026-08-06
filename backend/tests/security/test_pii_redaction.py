from backend.app.security.classification import (
    DataClassification,
    EgressPolicyError,
    allow_model_egress,
)
from backend.app.security.pii import redact_sensitive_text


def test_restricted_content_cannot_leave_through_a_third_party_model() -> None:
    try:
        allow_model_egress(DataClassification.RESTRICTED, provider_is_third_party=True)
    except EgressPolicyError as error:
        assert str(error) == "restricted_egress_denied"
    else:
        raise AssertionError("restricted egress must be denied")


def test_redaction_covers_chinese_phone_email_and_bearer_tokens_without_masking_stock_codes() -> None:
    text = "股票 600519，电话 13800138000，邮箱 a@example.com，Bearer secret-token-value"
    output = redact_sensitive_text(text)
    assert "600519" in output
    assert "13800138000" not in output
    assert "a@example.com" not in output
    assert "secret-token-value" not in output
