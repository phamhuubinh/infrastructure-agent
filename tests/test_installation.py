from __future__ import annotations

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
