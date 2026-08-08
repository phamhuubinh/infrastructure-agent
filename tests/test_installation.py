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


def test_reverse_proxy_is_bound_to_localhost() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())

    assert compose["services"]["reverse-proxy"]["ports"] == ["127.0.0.1:80:80"]


def test_source_archive_uses_only_committed_files() -> None:
    archive_script = (ROOT / "scripts/build-source-archive").read_text()

    assert 'git status --porcelain --untracked-files=normal' in archive_script
    assert "git archive --format=tar.gz" in archive_script


def test_source_archive_rejects_untracked_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    script = repo / "build-source-archive"
    script.write_text((ROOT / "scripts/build-source-archive").read_text())
    (repo / "tracked.txt").write_text("tracked\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "build-source-archive", "tracked.txt"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-qm", "initial"],
        cwd=repo,
        check=True,
    )
    (repo / "untracked.py").write_text("important = True\n")

    result = subprocess.run(
        ["bash", str(script)], cwd=repo, capture_output=True, text=True
    )

    assert result.returncode == 2
    assert "Refusing to archive a dirty working tree." in result.stderr


def test_api_image_bundles_safe_tool_registry_and_mounts_credentials() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    api = compose["services"]["api"]
    dockerfile = (ROOT / "docker/Dockerfile.api").read_text()
    dockerignore = (ROOT / ".dockerignore").read_text().splitlines()
    tool_config = json.loads((ROOT / "tools.json").read_text())

    assert "COPY tools.json ." in dockerfile
    assert "COPY pyproject.toml uv.lock ." in dockerfile
    assert "uv sync --frozen --no-dev --extra web" in dockerfile
    assert "USER orion" in dockerfile
    assert "uv.lock" not in dockerignore
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
    assert api["environment"]["ORION_SERVERS_FILE"] == (
        "/home/orion/.orion/servers.json"
    )
    assert api["volumes"] == ["orion-data:/home/orion/.orion"]
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


def test_rag_image_uses_its_frozen_lock_without_test_dependencies() -> None:
    rag_root = ROOT / "src/tool/RAGTool"
    dockerfile = (rag_root / "Dockerfile").read_text()
    pyproject = (rag_root / "pyproject.toml").read_text()

    assert "COPY pyproject.toml uv.lock ." in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER orion" in dockerfile
    assert 'requires-python = ">=3.12,<3.13"' in pyproject
    assert "[dependency-groups]" in pyproject
    assert not (rag_root / "requirements.txt").exists()


def test_desktop_uses_the_authenticated_docker_reverse_proxy() -> None:
    desktop_root = ROOT / "desktop"
    main = (desktop_root / "main.js").read_text()
    proxy = (desktop_root / "orion-docker.js").read_text()
    package = json.loads((desktop_root / "package.json").read_text())

    assert 'ORION_DOCKER_ORIGIN = "http://127.0.0.1:80"' in proxy
    assert "getOrionDockerTarget(pathname, url.search)" in main
    assert "BACKEND_PORT" not in main
    assert package["scripts"]["test"] == "node --test"
    assert package["scripts"]["package"] == "electron-builder"
    assert package["build"]["win"]["target"] == ["nsis"]


def test_orion_has_no_model_install_api_or_cli() -> None:
    router = (ROOT / "src/backend/routers/models.py").read_text()
    cli = (ROOT / "src/cli/main.py").read_text()

    assert "/install/ollama" not in router
    assert 'model_sub.add_parser("install"' not in cli


def test_uninstaller_is_valid_and_documents_full_cleanup() -> None:
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

    assert "Completely remove Orion" in result.stdout
    assert "runtime cleanup is now the default" in result.stdout
    assert "model" in result.stdout
    assert "connections, sessions, RAG projects" in result.stdout
    assert "--yes preserves it" in result.stdout
    assert "source directory" in result.stdout

    non_interactive = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
    )
    assert non_interactive.returncode == 2
    assert "requires --yes" in non_interactive.stderr

    dry_run = subprocess.run(
        ["bash", str(script), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Dry run complete" in dry_run.stdout


def test_installer_creates_host_cli_launcher() -> None:
    installer = (ROOT / "install.sh").read_text()
    launcher_installer = (ROOT / "scripts/install-cli").read_text()
    launcher = (ROOT / "scripts/orion").read_text()

    assert '"$PROJECT_DIR/scripts/install-cli"' in installer
    assert "# Orion CLI launcher managed by Orion" in launcher_installer
    assert 'exec docker "${compose_args[@]}" api orion "$@"' in launcher
    assert 'nohup xdg-open "$web_url"' in launcher
    assert 'nohup gio open "$web_url"' in launcher
    assert "docker compose up -d --no-build reverse-proxy" in launcher
    assert "web_log_since=\"$(date -u '+%Y-%m-%dT%H:%M:%SZ')\"" in launcher
    assert (
        'docker compose logs --follow --since "$web_log_since" ui api' in launcher
    )
    assert "docker compose stop reverse-proxy ui api" in launcher
    assert "exec docker compose logs --follow --tail=100" in launcher


def test_host_web_launcher_separates_web_and_all_service_logs(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    calls = tmp_path / "docker-calls"
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$DOCKER_CALLS\"\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    env = {
        "PATH": f"{fake_bin}:/usr/bin:/bin",
        "DOCKER_CALLS": str(calls),
        "ORION_DISABLE_BROWSER": "1",
    }

    web = subprocess.run(
        ["bash", str(ROOT / "scripts/orion"), "web"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    web_calls = calls.read_text().splitlines()
    assert "compose up -d --no-build reverse-proxy" in web_calls
    assert any(
        call.startswith("compose logs --follow --since ")
        and call.endswith(" ui api")
        for call in web_calls
    )
    assert not any(
        call.startswith("compose logs") and "reverse-proxy" in call
        for call in web_calls
    )
    assert "compose stop reverse-proxy ui api" in web_calls
    assert "Press Ctrl+C to stop the Web UI" in web.stdout

    calls.write_text("")
    logs = subprocess.run(
        ["bash", str(ROOT / "scripts/orion"), "log"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    log_calls = calls.read_text().splitlines()
    assert "compose logs --follow --tail=100" in log_calls
    assert not any(call.startswith("compose stop") for call in log_calls)
    assert "Orion keeps running" in logs.stdout


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


def test_uninstaller_removes_runtime_state_and_preserves_shared_credentials() -> None:
    uninstaller = (ROOT / "uninstall.sh").read_text()

    assert 'SYSTEM_TOOL_SECRETS_PATH="/etc/orion/tool-credentials.json"' in uninstaller
    assert 'rm -f -- "$SYSTEM_TOOL_SECRETS_PATH"' in uninstaller
    assert "REMOVE_CREDENTIALS=false" in uninstaller
    assert 'confirm_yes_no "Continue uninstall?"' in uninstaller
    assert 'confirm_yes_no "Also remove $SYSTEM_TOOL_SECRETS_PATH?"' in uninstaller
    assert 'y|yes) return 0' in uninstaller
    assert '""|n|no) return 1' in uninstaller
    assert "Type 'remove Orion'" not in uninstaller
    assert "Preserving shared Grafana/Zabbix credentials" in uninstaller
    assert "compose_args=(down --remove-orphans --rmi local --volumes)" in uninstaller
    assert 'rm -f -- "$PROJECT_DIR/.env"' in uninstaller
    assert 'rm -rf -- "$user_home/.orion"' in uninstaller
    assert 'rm -rf -- "/tmp/orion-rag"' in uninstaller
    assert '"orion_agent_orion-sessions"' in uninstaller
    assert '"orion_agent_orion-models"' in uninstaller
    assert '"orion_agent_dify-storage"' in uninstaller
    assert '"orion_agent_redis-data"' in uninstaller
    assert 'label=com.docker.compose.project=${compose_project}' in uninstaller
    assert "Persistent data was preserved" not in uninstaller


def test_api_image_installs_core_linux_collector_binaries() -> None:
    dockerfile = Path("docker/Dockerfile.api").read_text()

    for package in (
        "ca-certificates",
        "iproute2",
        "iputils-ping",
        "openssh-client",
        "procps",
        "util-linux",
    ):
        assert package in dockerfile
