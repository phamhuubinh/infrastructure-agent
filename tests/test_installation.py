from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_does_not_bundle_a_model_runtime() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]

    assert "ollama" not in services
    assert "orion-models" not in compose.get("volumes", {})
    api_environment = services["api"]["environment"]
    assert not any(key.startswith("OLLAMA_") for key in api_environment)


def test_api_image_bundles_safe_tool_registry_and_mounts_credentials() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["api"]
    dockerfile = (ROOT / "docker/Dockerfile.api").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()
    tool_config = json.loads((ROOT / "tools.json").read_text())

    assert "COPY tools.json ." in dockerfile
    assert "tools.json" not in dockerignore
    assert api["environment"]["ORION_SECRETS_PATH"] == (
        "/run/secrets/orion-tool-credentials.json"
    )
    assert api["secrets"] == [
        {
            "source": "orion-tool-credentials",
            "target": "orion-tool-credentials.json",
        }
    ]
    assert compose["secrets"]["orion-tool-credentials"]["file"] == (
        "${ORION_TOOL_SECRETS_FILE:-/etc/orion/tool-credentials.json}"
    )
    for entry in tool_config.values():
        assert "url" not in entry
        assert "token" not in entry


def test_ci_compose_uses_empty_tool_credentials_fixture() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.ci.yml").read_text())
    secret_file = compose["secrets"]["orion-tool-credentials"]["file"]

    assert secret_file == "./tests/data/empty_tool_credentials.json"
    assert json.loads((ROOT / secret_file).read_text()) == {}


def test_ui_image_runs_the_ssr_bundle() -> None:
    dockerfile = (ROOT / "docker/Dockerfile.ui").read_text()
    proxy = (ROOT / "docker/nginx-reverse-proxy.conf").read_text()

    assert 'CMD ["node", "server.mjs"]' in dockerfile
    assert "COPY --from=build /app/dist ./dist" in dockerfile
    assert "nginx:alpine" not in dockerfile
    assert "proxy_pass http://ui:3000;" in proxy


def test_orion_has_no_model_install_api_or_cli() -> None:
    router = (ROOT / "src/backend/routers/models.py").read_text()
    cli = (ROOT / "src/cli/main.py").read_text()

    assert "/install/ollama" not in router
    assert 'model_sub.add_parser("install"' not in cli


def test_uninstaller_is_valid_and_documents_purge_mode() -> None:
    script = ROOT / "uninstall.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    subprocess.run(["bash", "-n", str(ROOT / "scripts/orion")], check=True)
    subprocess.run(["bash", "-n", str(ROOT / "scripts/install-cli")], check=True)
    result = subprocess.run(
        ["bash", str(script), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--purge" in result.stdout
    assert "source directory" in result.stdout


def test_installer_creates_host_cli_launcher() -> None:
    installer = (ROOT / "install.sh").read_text()
    launcher_installer = (ROOT / "scripts/install-cli").read_text()
    launcher = (ROOT / "scripts/orion").read_text()

    assert '"$PROJECT_DIR/scripts/install-cli"' in installer
    assert "# Orion CLI launcher managed by Orion" in launcher_installer
    assert 'exec docker "${compose_args[@]}" api orion "$@"' in launcher
    assert 'nohup xdg-open "$web_url"' in launcher
    assert 'nohup gio open "$web_url"' in launcher


def test_installer_uses_external_tool_credentials_file() -> None:
    installer = (ROOT / "install.sh").read_text()

    assert "/etc/orion/tool-credentials.json" in installer
    assert 'ensure_env_value "ORION_TOOL_SECRETS_FILE"' in installer
    assert 'ensure_tool_credentials_file "$tool_secrets_path"' in installer
    assert "printf '{}\\n'" in installer
    assert 'install -D -m 600' in installer
    assert "Grafana/Zabbix setup skipped" in installer
    assert '(("grafana", "Grafana"), ("zabbix", "Zabbix"))' in installer
    assert "connection disabled (missing:" in installer


def test_uninstaller_purges_default_external_tool_credentials() -> None:
    uninstaller = (ROOT / "uninstall.sh").read_text()

    assert 'SYSTEM_TOOL_SECRETS_PATH="/etc/orion/tool-credentials.json"' in uninstaller
    assert 'rm -f -- "$SYSTEM_TOOL_SECRETS_PATH"' in uninstaller
