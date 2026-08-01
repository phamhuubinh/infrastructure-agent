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

umask 077
ensure_env_value "POSTGRES_USER" "orion"
ensure_env_value "POSTGRES_PASSWORD" "$(random_hex)"
ensure_env_value "POSTGRES_DB" "orion"
ensure_env_value "ORION_API_KEY" "$(random_hex)"
echo "Private runtime configuration is ready in .env"

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
if [[ "$model_choice" == "skip" ]]; then
    echo "No model was configured. Connect a user-managed model later in Settings or with:"
    echo "  docker compose exec api orion model --help"
fi
