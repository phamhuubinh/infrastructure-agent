#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Docker Engine with Docker Compose is required to install Orion." >&2
    exit 1
fi

random_hex() {
    od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
}

touch .env
chmod 600 .env 2>/dev/null || true

ensure_env_value() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" .env; then
        if [[ -z "$(sed -n "s/^${key}=//p" .env | tail -n 1)" ]]; then
            sed -i "s/^${key}=.*/${key}=${value}/" .env
        fi
    else
        echo "${key}=${value}" >> .env
    fi
}

run_privileged() {
    if ((EUID == 0)); then
        "$@"
        return
    fi
    if command -v sudo >/dev/null 2>&1; then
        sudo "$@"
        return
    fi
    "$@"
}

ensure_tool_credentials_group() {
    local group_name="orion-tool-secrets"
    local group_entry
    local group_gid

    if ! command -v getent >/dev/null 2>&1; then
        echo "getent is required to configure the Orion tool-credentials group." >&2
        exit 1
    fi

    group_entry="$(getent group "$group_name" || true)"
    if [[ -z "$group_entry" ]]; then
        if ! command -v groupadd >/dev/null 2>&1; then
            echo "groupadd is required to create the Orion tool-credentials group." >&2
            exit 1
        fi
        if ! run_privileged groupadd --system "$group_name"; then
            echo "Failed to create the Orion tool-credentials group." >&2
            exit 1
        fi
        group_entry="$(getent group "$group_name" || true)"
    fi

    group_gid="$(printf '%s\n' "$group_entry" | cut -d: -f3)"
    if [[ ! "$group_gid" =~ ^[0-9]+$ ]]; then
        echo "Unable to resolve numeric GID for $group_name." >&2
        exit 1
    fi
    printf '%s\n' "$group_gid"
}

ensure_tool_credentials_file() {
    local credentials_path="$1"
    local credentials_gid="$2"
    local empty_credentials
    local installer_uid

    if [[ "$credentials_path" != /* ]]; then
        echo "ORION_TOOL_SECRETS_FILE must be an absolute path: $credentials_path" >&2
        exit 1
    fi
    if [[ ! "$credentials_gid" =~ ^[0-9]+$ ]]; then
        echo "ORION_TOOL_SECRETS_GID must be numeric: $credentials_gid" >&2
        exit 1
    fi
    if [[ -e "$credentials_path" && ! -f "$credentials_path" ]]; then
        echo "Tool credentials path is not a regular file: $credentials_path" >&2
        exit 1
    fi

    if [[ -f "$credentials_path" ]]; then
        if ! run_privileged chgrp "$credentials_gid" "$credentials_path" \
                || ! run_privileged chmod 640 "$credentials_path"; then
            echo "Failed to secure tool credentials at $credentials_path" >&2
            exit 1
        fi
        echo "Using external tool credentials at $credentials_path"
        return
    fi

    empty_credentials="$(mktemp)"
    printf '{}\n' > "$empty_credentials"
    installer_uid="${SUDO_UID:-$(id -u)}"
    if ! run_privileged install -D -m 640 \
            -o "$installer_uid" -g "$credentials_gid" \
            "$empty_credentials" "$credentials_path"; then
        rm -f -- "$empty_credentials"
        echo "Failed to install tool credentials at $credentials_path" >&2
        exit 1
    fi
    rm -f -- "$empty_credentials"
    echo "Created empty tool credentials at $credentials_path"
    echo "Grafana/Zabbix setup skipped; you can add their URLs and tokens later."
}

report_tool_credentials() {
    if ! docker compose exec -T api python3 - <<'PY'
from src.shared.config import get_config

tools = get_config().tools
for name, label in (("grafana", "Grafana"), ("zabbix", "Zabbix")):
    entry = tools.get(name, {})
    missing = [field for field in ("url", "token") if not entry.get(field)]
    if missing:
        print(f"WARNING: {label} connection disabled (missing: {', '.join(missing)})")
    else:
        print(f"OK: {label} credentials loaded")
PY
    then
        echo "Warning: unable to inspect Grafana/Zabbix credential status." >&2
    fi
}

umask 077
ensure_env_value "POSTGRES_USER" "orion"
ensure_env_value "POSTGRES_PASSWORD" "$(random_hex)"
ensure_env_value "POSTGRES_DB" "orion"
ensure_env_value "ORION_API_KEY" "$(random_hex)"
env_tool_secrets_path="$(sed -n 's/^ORION_TOOL_SECRETS_FILE=//p' .env | tail -n 1)"
tool_secrets_path="${ORION_TOOL_SECRETS_FILE:-${env_tool_secrets_path:-/etc/orion/tool-credentials.json}}"
env_tool_secrets_gid="$(sed -n 's/^ORION_TOOL_SECRETS_GID=//p' .env | tail -n 1)"
tool_secrets_gid="${ORION_TOOL_SECRETS_GID:-${env_tool_secrets_gid:-}}"
if [[ -z "$tool_secrets_gid" ]]; then
    tool_secrets_gid="$(ensure_tool_credentials_group)"
fi
ensure_env_value "ORION_TOOL_SECRETS_FILE" "$tool_secrets_path"
ensure_env_value "ORION_TOOL_SECRETS_GID" "$tool_secrets_gid"
echo "Private runtime configuration is ready in .env"

ensure_tool_credentials_file "$tool_secrets_path" "$tool_secrets_gid"

"$PROJECT_DIR/scripts/install-cli"

model_choice="skip"
if [[ -t 0 ]]; then
    echo
    echo "Model setup (Orion can be installed without a model):"
    echo "  1) Skip for now"
    echo "  2) Connect an existing OpenAI-compatible model"
    read -r -p "Choose [1]: " answer
    case "${answer:-1}" in
        2)
            model_choice="external"
            read -r -p "Connection name [primary]: " connection_name
            connection_name="${connection_name:-primary}"
            read -r -p "Base URL (with or without /v1): " model_base_url
            while [[ -z "$model_base_url" ]]; do
                read -r -p "Base URL is required: " model_base_url
            done
            read -r -p "Model name: " model_name
            while [[ -z "$model_name" ]]; do
                read -r -p "Model name is required: " model_name
            done
            read -r -s -p "API key (Enter if not required): " model_api_key
            echo
            ;;
    esac
fi

echo "Starting the complete Orion application..."
docker compose up -d --build --remove-orphans
report_tool_credentials

if [[ "$model_choice" == "external" ]]; then
    docker compose exec -T api orion model add "$connection_name" \
        --provider openai \
        --base-url "$model_base_url" \
        --model "$model_name" \
        --api-key-stdin <<< "$model_api_key"
    if ! docker compose exec -T api orion model test "$connection_name"; then
        echo "Warning: Orion was installed, but the model connection test failed." >&2
    fi
fi

echo
echo "Orion is installed at http://localhost"
echo "CLI: orion help"
echo "Grafana/Zabbix credentials: $tool_secrets_path"
echo "After changing tool credentials, run: docker compose up -d --force-recreate api"
if [[ "$model_choice" == "skip" ]]; then
    echo "No model was configured. Connect a user-managed model later in Settings or with:"
    echo "  docker compose exec api orion model --help"
fi
