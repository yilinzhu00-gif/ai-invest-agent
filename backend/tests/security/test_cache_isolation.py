from backend.app.core.cache import secure_cache_key


def test_cache_key_isolated_by_workspace_and_acl_revision() -> None:
    first = secure_cache_key("workspace-a", "acl-1", "input", "model", "prompt", "retrieval", "2026-08-06")
    second = secure_cache_key("workspace-b", "acl-2", "input", "model", "prompt", "retrieval", "2026-08-06")
    assert first != second
