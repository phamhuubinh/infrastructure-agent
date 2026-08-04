#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEM_TOOL_SECRETS_PATH="/etc/orion/tool-credentials.json"
ASSUME_YES=false
DRY_RUN=false
CLEANUP_INCOMPLETE=false
REMOVE_CREDENTIALS=false

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [--yes] [--dry-run]

Completely remove Orion while keeping only this source directory.

  --yes      Do not ask for confirmation.
  --dry-run  Print the actions without changing the machine.
  --purge    Deprecated compatibility alias; runtime cleanup is now the default.
  -h, --help Show this help message.

This deletes Orion containers, networks, project-built images, volumes, model
connections, sessions, RAG projects, logs, and private runtime configuration.
Interactive uninstall separately asks whether to remove the shared Grafana/
Zabbix credential file; --yes preserves it. User-managed external model
runtimes and this source directory are not deleted.
EOF
}

while (($#)); do
    case "$1" in
        --purge) ;;
        --yes|-y) ASSUME_YES=true ;;
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

run() {
    if [[ "$DRY_RUN" == true ]]; then
        printf 'Would run:'
        printf ' %q' "$@"
        printf '\n'
        return 0
    fi
    "$@"
}

confirm_yes_no() {
    local prompt="$1"
    local answer

    while true; do
        read -r -p "$prompt [y/N]: " answer || return 1
        case "${answer,,}" in
            y|yes) return 0 ;;
            ""|n|no) return 1 ;;
            *) echo "Please answer y/yes or n/no." ;;
        esac
    done
}

if [[ "$ASSUME_YES" != true && "$DRY_RUN" != true ]]; then
    if [[ ! -t 0 ]]; then
        echo "Non-interactive uninstall requires --yes." >&2
        exit 2
    fi
    echo "This will permanently delete all Orion sessions, RAG projects, model"
    echo "connections, database data, logs, private runtime data, and legacy"
    echo "Ollama artifacts created by Orion."
    if ! confirm_yes_no "Continue uninstall?"; then
        echo "Uninstall cancelled."
        exit 0
    fi
    if confirm_yes_no "Also remove $SYSTEM_TOOL_SECRETS_PATH?"; then
        REMOVE_CREDENTIALS=true
    fi
fi

cd "$PROJECT_DIR"

if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        echo "Removing Orion containers, network, and project-built images..."
        if docker compose version >/dev/null 2>&1; then
            compose_args=(down --remove-orphans --rmi local --volumes)
            if ! run env \
                POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orion-uninstall-only}" \
                ORION_API_KEY="${ORION_API_KEY:-orion-uninstall-only}" \
                ORION_TOOL_SECRETS_FILE="$PROJECT_DIR/config/tool-credentials.example.json" \
                docker compose "${compose_args[@]}"; then
                echo "Warning: Compose cleanup was incomplete; continuing with known Orion resources." >&2
                [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
            fi
        else
            echo "Warning: Docker Compose is unavailable; continuing with known Orion resources." >&2
            [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
        fi

        project_name="${COMPOSE_PROJECT_NAME:-}"
        if [[ -z "$project_name" ]]; then
            project_name="$(basename "$PROJECT_DIR")"
        fi
        project_name="${project_name,,}"
        orion_containers=(
            "orion-reverse-proxy"
            "orion-api"
            "orion-ui"
            "orion-pg"
            "orion-rag-service"
            "orion-dify-api"
            "orion-dify-web"
            "orion-redis"
        )
        for compose_project in "$project_name" "orion_agent"; do
            while IFS= read -r labeled_container; do
                [[ -z "$labeled_container" ]] || orion_containers+=("$labeled_container")
            done < <(
                docker ps -a \
                    --filter "label=com.docker.compose.project=${compose_project}" \
                    --format '{{.Names}}'
            )
        done
        declare -A seen_containers=()
        for container in "${orion_containers[@]}"; do
            if [[ -n "${seen_containers[$container]:-}" ]]; then
                continue
            fi
            seen_containers["$container"]=true
            if docker container inspect "$container" >/dev/null 2>&1; then
                echo "Removing Orion container: $container"
                if ! run docker container rm -f "$container"; then
                    echo "Warning: Orion container could not be removed: $container" >&2
                    [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
                fi
            fi
        done

        orion_networks=(
            "orion_agent_default"
            "${project_name}_default"
        )
        for compose_project in "$project_name" "orion_agent"; do
            while IFS= read -r labeled_network; do
                [[ -z "$labeled_network" ]] || orion_networks+=("$labeled_network")
            done < <(
                docker network ls \
                    --filter "label=com.docker.compose.project=${compose_project}" \
                    --format '{{.Name}}'
            )
        done
        declare -A seen_networks=()
        for network in "${orion_networks[@]}"; do
            if [[ -n "${seen_networks[$network]:-}" ]]; then
                continue
            fi
            seen_networks["$network"]=true
            if docker network inspect "$network" >/dev/null 2>&1; then
                echo "Removing Orion network: $network"
                if ! run docker network rm "$network"; then
                    echo "Warning: Orion network could not be removed: $network" >&2
                    [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
                fi
            fi
        done

        orion_volumes=(
            "orion-data"
            "orion-pgdata"
            "orion-ragdata"
            "orion-sessions"
            "orion-models"
            "orion_agent_orion-data"
            "orion_agent_orion-pgdata"
            "orion_agent_orion-ragdata"
            "orion_agent_orion-sessions"
            "orion_agent_orion-models"
            "orion_agent_dify-storage"
            "orion_agent_redis-data"
            "${project_name}_orion-data"
            "${project_name}_orion-pgdata"
            "${project_name}_orion-ragdata"
            "${project_name}_orion-sessions"
            "${project_name}_orion-models"
            "${project_name}_dify-storage"
            "${project_name}_redis-data"
        )
        for compose_project in "$project_name" "orion_agent"; do
            while IFS= read -r labeled_volume; do
                [[ -z "$labeled_volume" ]] || orion_volumes+=("$labeled_volume")
            done < <(
                docker volume ls \
                    --filter "label=com.docker.compose.project=${compose_project}" \
                    --format '{{.Name}}'
            )
        done
        declare -A seen_volumes=()
        for volume in "${orion_volumes[@]}"; do
            if [[ -n "${seen_volumes[$volume]:-}" ]]; then
                continue
            fi
            seen_volumes["$volume"]=true
            if docker volume inspect "$volume" >/dev/null 2>&1; then
                echo "Removing Orion volume: $volume"
                if ! run docker volume rm "$volume"; then
                    echo "Warning: Orion volume is still in use: $volume" >&2
                    [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
                fi
            fi
        done
        if docker image inspect ollama/ollama:latest >/dev/null 2>&1; then
            echo "Removing the legacy Ollama image pulled by Orion..."
            if ! run docker image rm ollama/ollama:latest; then
                echo "Warning: the Ollama image is still used outside Orion; it was preserved." >&2
            fi
        fi

        orion_image_repositories=(
            "orion-api"
            "orion-ui"
            "orion-rag"
            "orion-rag-service"
            "${project_name}-api"
            "${project_name}-ui"
            "${project_name}-rag-service"
            "${project_name}-dify-api"
            "${project_name}-dify-web"
        )
        for repository in "${orion_image_repositories[@]}"; do
            while IFS= read -r image_ref; do
                [[ -z "$image_ref" ]] && continue
                echo "Removing Orion image: $image_ref"
                if ! run docker image rm "$image_ref"; then
                    echo "Warning: Orion image is still in use: $image_ref" >&2
                    [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
                fi
            done < <(
                docker images \
                    --filter "reference=${repository}:*" \
                    --format '{{.Repository}}:{{.Tag}}'
            )
        done
    else
        echo "Warning: Docker is unavailable; Docker resources were not removed." >&2
        [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
    fi
else
    echo "Warning: Docker command is unavailable; Docker resources were not removed." >&2
    [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
fi

if command -v python3 >/dev/null 2>&1; then
    editable_location="$({ python3 -m pip show orion 2>/dev/null || true; } | sed -n 's/^Editable project location: //p' | tail -n 1)"
    if [[ "$editable_location" == "$PROJECT_DIR" ]]; then
        echo "Removing the editable Orion CLI installation..."
        if ! run python3 -m pip uninstall -y orion; then
            echo "Warning: the editable Orion CLI could not be removed." >&2
            [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
        fi
    fi
fi

user_home="${HOME:-}"
if [[ -n "$user_home" && "$user_home" != "/" ]]; then
    cli_path="$user_home/.local/bin/orion"
    remove_cli=false
    if [[ -L "$cli_path" ]]; then
        cli_target="$(readlink -f "$cli_path" 2>/dev/null || true)"
        if [[ "$cli_target" == "$PROJECT_DIR/scripts/orion" ]]; then
            remove_cli=true
        fi
    elif [[ -f "$cli_path" ]] && grep -qFx \
        "# Orion CLI launcher managed by Orion" "$cli_path"; then
        remove_cli=true
    fi
    if [[ "$remove_cli" == true ]]; then
        echo "Removing the Orion CLI launcher..."
        run rm -f -- "$cli_path"
    fi
fi

echo "Removing Orion private configuration and runtime data..."
run rm -f -- "$PROJECT_DIR/.env"
run rm -f -- "$PROJECT_DIR/docker-compose.env"
run rm -f -- "$PROJECT_DIR/servers.json"
run rm -f -- "$PROJECT_DIR/config/secrets.local.json"

if [[ "$REMOVE_CREDENTIALS" == true && -f "$SYSTEM_TOOL_SECRETS_PATH" ]]; then
    if ((EUID == 0)); then
        run rm -f -- "$SYSTEM_TOOL_SECRETS_PATH"
        run rmdir --ignore-fail-on-non-empty -- "$(dirname "$SYSTEM_TOOL_SECRETS_PATH")"
    elif command -v sudo >/dev/null 2>&1; then
        run sudo rm -f -- "$SYSTEM_TOOL_SECRETS_PATH"
        run sudo rmdir --ignore-fail-on-non-empty -- "$(dirname "$SYSTEM_TOOL_SECRETS_PATH")"
    else
        echo "Warning: could not remove $SYSTEM_TOOL_SECRETS_PATH without sudo." >&2
        [[ "$DRY_RUN" == true ]] || CLEANUP_INCOMPLETE=true
    fi
elif [[ -f "$SYSTEM_TOOL_SECRETS_PATH" ]]; then
    echo "Preserving shared Grafana/Zabbix credentials: $SYSTEM_TOOL_SECRETS_PATH"
fi

if [[ -n "$user_home" && "$user_home" != "/" && -d "$user_home/.orion" ]]; then
    run rm -rf -- "$user_home/.orion"
fi

if [[ -d "/tmp/orion-rag" ]]; then
    run rm -rf -- "/tmp/orion-rag"
fi

if [[ "$CLEANUP_INCOMPLETE" == true ]]; then
    echo "Orion uninstall is incomplete; review the warnings above." >&2
    exit 1
fi

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run complete; no files or Docker resources were changed."
else
    echo "Orion has been completely uninstalled. Source code was preserved at: $PROJECT_DIR"
fi
