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
