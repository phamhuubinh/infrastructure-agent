#!/usr/bin/env bash
# Run benchmark suite with timeout
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "[benchmark] Running benchmark suite..."
timeout 120 python3 -m benchmark --domain assessment --json 2>&1 || echo "[benchmark] TIMEOUT or FAILED"
echo "[benchmark] Done"
