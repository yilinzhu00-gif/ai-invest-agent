import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_operational_scripts_are_valid_shell_and_do_not_target_production_by_default() -> None:
    for name in ("smoke-test.sh", "verify-migrations.sh"):
        path = ROOT / "scripts" / name
        assert path.exists()
        assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0
    assert "refusing non-test target" in (ROOT / "scripts" / "smoke-test.sh").read_text()
