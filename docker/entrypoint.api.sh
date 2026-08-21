#!/bin/sh
set -eu

config_path="${ORION_SERVERS_FILE:-/home/orion/.orion/servers.json}"
config_dir=$(dirname "$config_path")
mkdir -p "$config_dir"
if [ ! -f "$config_path" ]; then
    cp /app/servers.default.json "$config_path"
    chmod 600 "$config_path" 2>/dev/null || true
fi

targets_path="${ORION_TARGETS_FILE:-/app/targets.json}"
if [ "$targets_path" != "/app/targets.json" ] && [ ! -f "$targets_path" ]; then
    targets_dir=$(dirname "$targets_path")
    mkdir -p "$targets_dir"
    cp /app/targets.json "$targets_path"
    chmod 600 "$targets_path" 2>/dev/null || true
fi

exec "$@"
