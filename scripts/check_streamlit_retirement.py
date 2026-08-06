"""Prevent new Streamlit application work before the separately approved retirement PR."""

import subprocess
from pathlib import Path


def changed_legacy_paths_are_allowed(paths: list[Path]) -> bool:
    return not any(path.parts and path.parts[0] == "legacy" for path in paths)


def main() -> None:
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD^", "HEAD"], text=True
    ).splitlines()
    if not changed_legacy_paths_are_allowed([Path(path) for path in changed]):
        raise SystemExit("Streamlit legacy files may only change in a separately approved retirement PR.")


if __name__ == "__main__":
    main()
