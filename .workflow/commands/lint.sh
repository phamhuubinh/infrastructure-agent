#!/usr/bin/env bash
# Lint Python source with ruff
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "[lint] Running ruff check on src/"
ruff check src/ --select ALL --ignore D --ignore INP --ignore S --ignore E501 2>&1 || true
echo "[lint] Done"
