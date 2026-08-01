#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PURGE=false
ASSUME_YES=false
DRY_RUN=false

usage() {
    cat <<'EOF'
Usage: ./uninstall.sh [--purge] [--yes] [--dry-run]

Remove the Orion application while keeping this source directory.

  --purge    Also delete Orion volumes, runtime data, private configuration,
             and legacy Ollama artifacts previously created by Orion.
  --yes      Do not ask for confirmation when --purge is used.
  --dry-run  Print the actions without changing the machine.
  -h, --help Show this help message.

Without --purge, Docker volumes and private configuration are preserved so a
later installation can reuse them.
EOF
}

while (($#)); do
    case "$1" in
        --purge) PURGE=true ;;
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

if [[ "$PURGE" == true && "$ASSUME_YES" != true ]]; then
    if [[ ! -t 0 ]]; then
        echo "--purge in non-interactive mode requires --yes." >&2
        exit 2
    fi
    echo "This will permanently delete all Orion sessions, RAG projects, model"
    echo "connections, database data, logs, secrets, and legacy Ollama data."
    read -r -p "Type 'remove Orion' to continue: " confirmation
    if [[ "$confirmation" != "remove Orion" ]]; then
        echo "Uninstall cancelled."
        exit 0
    fi
fi

cd "$PROJECT_DIR"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        echo "Removing Orion containers, network, and project-built images..."
        compose_args=(down --remove-orphans --rmi local)
        if [[ "$PURGE" == true ]]; then
            compose_args+=(--volumes)
        fi
        if ! run env \
            POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-orion-uninstall-only}" \
            ORION_API_KEY="${ORION_API_KEY:-orion-uninstall-only}" \
            docker compose "${compose_args[@]}"; then
            echo "Warning: Compose cleanup was incomplete; continuing with known Orion resources." >&2
        fi

        if [[ "$PURGE" == true ]]; then
            project_name="${COMPOSE_PROJECT_NAME:-}"
            if [[ -z "$project_name" ]]; then
                project_name="$(basename "$PROJECT_DIR")"
            fi
            project_name="${project_name,,}"
            orion_volumes=(
                "orion_agent_orion-data"
                "orion_agent_orion-pgdata"
                "orion_agent_orion-ragdata"
                "orion_agent_orion-sessions"
                "orion_agent_orion-models"
                "${project_name}_orion-data"
                "${project_name}_orion-pgdata"
                "${project_name}_orion-ragdata"
                "${project_name}_orion-sessions"
                "${project_name}_orion-models"
            )
            for volume in "${orion_volumes[@]}"; do
                if docker volume inspect "$volume" >/dev/null 2>&1; then
                    echo "Removing Orion volume: $volume"
                    if ! run docker volume rm "$volume"; then
                        echo "Warning: Orion volume is still in use: $volume" >&2
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
            )
            for repository in "${orion_image_repositories[@]}"; do
                while IFS= read -r image_ref; do
                    [[ -z "$image_ref" ]] && continue
                    echo "Removing Orion image: $image_ref"
                    if ! run docker image rm "$image_ref"; then
                        echo "Warning: Orion image is still in use: $image_ref" >&2
                    fi
                done < <(
                    docker images \
                        --filter "reference=${repository}:*" \
                        --format '{{.Repository}}:{{.Tag}}'
                )
            done
        fi
    else
        echo "Warning: Docker is unavailable; Docker resources were not removed." >&2
    fi
fi

if command -v python3 >/dev/null 2>&1; then
    editable_location="$({ python3 -m pip show orion 2>/dev/null || true; } | sed -n 's/^Editable project location: //p' | tail -n 1)"
    if [[ "$editable_location" == "$PROJECT_DIR" ]]; then
        echo "Removing the editable Orion CLI installation..."
        if ! run python3 -m pip uninstall -y orion; then
            echo "Warning: the editable Orion CLI could not be removed." >&2
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

if [[ "$PURGE" == true ]]; then
    echo "Removing Orion private configuration and runtime data..."
    run rm -f -- "$PROJECT_DIR/.env"
    run rm -f -- "$PROJECT_DIR/servers.json"
    run rm -f -- "$PROJECT_DIR/config/secrets.local.json"

    if [[ -n "$user_home" && "$user_home" != "/" && -d "$user_home/.orion" ]]; then
        run rm -rf -- "$user_home/.orion"
    fi
fi

echo "Orion has been uninstalled. Source code was preserved at: $PROJECT_DIR"
if [[ "$PURGE" != true ]]; then
    echo "Persistent data was preserved. Use ./uninstall.sh --purge to delete it."
fi
