from pathlib import Path

from scripts.check_streamlit_retirement import changed_legacy_paths_are_allowed


def test_streamlit_gate_allows_only_documented_retirement_files() -> None:
    assert changed_legacy_paths_are_allowed([Path("docs/architecture/streamlit-parity.md")])
    assert not changed_legacy_paths_are_allowed([Path("legacy/app.py")])
