import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_operational_scripts_are_valid_shell_and_do_not_target_production_by_default() -> None:
    for name in ("smoke-test.sh", "verify-migrations.sh"):
        path = ROOT / "scripts" / name
        assert path.exists()
        assert subprocess.run(["bash", "-n", str(path)], check=False).returncode == 0
    assert "refusing non-test target" in (ROOT / "scripts" / "smoke-test.sh").read_text()


def test_observability_stack_has_collector_prometheus_and_provisioned_grafana_dashboard() -> None:
    compose = (ROOT / "deploy" / "compose.prod.yml").read_text()
    collector = (ROOT / "deploy" / "otel-collector.yml").read_text()
    prometheus = (ROOT / "deploy" / "prometheus.yml").read_text()
    dashboard = ROOT / "deploy" / "grafana" / "dashboards" / "investment-agent-overview.json"

    assert "otel-collector:" in compose
    assert "prometheus:" in compose
    assert "grafana:" in compose
    assert "otlp:" in collector
    assert "otel-collector:8889" in prometheus
    assert dashboard.exists()


def test_k6_load_runner_writes_machine_readable_summary() -> None:
    script = ROOT / "load" / "k6" / "agent_runs.js"
    runner = ROOT / "scripts" / "run-k6.sh"

    assert script.exists()
    assert "http.batch" in script.read_text()
    assert "--summary-export" in runner.read_text()
    assert subprocess.run(["bash", "-n", str(runner)], check=False).returncode == 0


def test_backup_restore_drill_is_test_only_and_checks_postgres_and_object_storage() -> None:
    drill = ROOT / "scripts" / "backup-restore-drill.sh"

    assert drill.exists()
    source = drill.read_text()
    assert "DRILL_ENV" in source
    assert "pg_dump" in source
    assert "pg_restore" in source
    assert "minio/mc" in source
    assert subprocess.run(["bash", "-n", str(drill)], check=False).returncode == 0
