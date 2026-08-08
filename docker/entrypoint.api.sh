#!/bin/sh
set -eu

config_path="${ORION_SERVERS_FILE:-/home/orion/.orion/servers.json}"
config_dir=$(dirname "$config_path")
mkdir -p "$config_dir"
if [ ! -f "$config_path" ]; then
    cp /app/servers.default.json "$config_path"
    chmod 600 "$config_path" 2>/dev/null || true
fi

exec "$@"
