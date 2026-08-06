from backend.app.prompts.manifest import build_context, load_prompt_manifest


def test_manifest_hashes_prompt_and_context_keeps_safety_and_request() -> None:
    """A budget trimmer must not remove either safety rules or the current user request."""
    manifest = load_prompt_manifest("analyst", "v1")
    context = build_context(
        safety_rules="SAFETY",
        current_request="CURRENT",
        run_state="STATE",
        evidence=["EVIDENCE-ONE", "EVIDENCE-TWO"],
        conversation_summary="SUMMARY",
        max_characters=24,
    )

    assert manifest.prompt_id == "analyst"
    assert len(manifest.sha256) == 64
    assert "SAFETY" in context
    assert "CURRENT" in context
    assert "EVIDENCE-ONE" not in context
