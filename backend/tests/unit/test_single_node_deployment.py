import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_single_node_compose_exposes_only_nginx_and_keeps_internal_services_private() -> None:
    compose = (ROOT / "deploy" / "compose.single-node.yml").read_text()

    assert "nginx:" in compose
    assert "NGINX_ENVSUBST_FILTER" in compose
    assert '"80:80"' in compose
    assert '"443:443"' in compose
    assert '"5432:5432"' not in compose
    assert '"6379:6379"' not in compose
    assert "api:" in compose
    assert "frontend:" in compose


def test_nginx_tls_template_proxies_api_sse_without_buffering() -> None:
    template = (ROOT / "deploy" / "nginx" / "default.conf.template").read_text()

    assert "ssl_certificate" in template
    assert "proxy_buffering off" in template
    assert "proxy_pass http://api:8000" in template
    assert "proxy_pass http://frontend:3000" in template
    assert "Strict-Transport-Security" in template


def test_single_node_environment_and_verifier_do_not_accept_plain_http() -> None:
    environment = (ROOT / "deploy" / "env" / "single-node.example").read_text()
    verifier = ROOT / "scripts" / "verify-single-node-deployment.sh"

    assert "APP_ENV=production" in environment
    assert "OIDC_ISSUER" in environment
    assert "NEXT_PUBLIC_OIDC_CLIENT_ID" in environment
    assert "https://" in verifier.read_text()
    assert subprocess.run(["bash", "-n", str(verifier)], check=False).returncode == 0


def test_frontend_image_receives_public_oidc_build_arguments() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    compose = (ROOT / "deploy" / "compose.base.yml").read_text()

    for variable in (
        "NEXT_PUBLIC_OIDC_AUTHORITY",
        "NEXT_PUBLIC_OIDC_CLIENT_ID",
        "NEXT_PUBLIC_OIDC_SCOPE",
        "NEXT_PUBLIC_DEFAULT_WORKSPACE_ID",
    ):
        assert f"ARG {variable}" in dockerfile
        assert variable in compose


def test_frontend_auth_mode_must_be_explicit_across_deployment_inputs() -> None:
    dockerfile_lines = (ROOT / "frontend" / "Dockerfile").read_text().splitlines()
    compose = (ROOT / "deploy" / "compose.base.yml").read_text()
    single_node_environment = (ROOT / "deploy" / "env" / "single-node.example").read_text()

    assert "ARG NEXT_PUBLIC_AUTH_MODE" in dockerfile_lines
    assert not any(line.startswith("ARG NEXT_PUBLIC_AUTH_MODE=") for line in dockerfile_lines)
    assert "NEXT_PUBLIC_AUTH_MODE: ${NEXT_PUBLIC_AUTH_MODE:?NEXT_PUBLIC_AUTH_MODE must be set}" in compose
    assert "NEXT_PUBLIC_AUTH_MODE=oidc" in single_node_environment.splitlines()
