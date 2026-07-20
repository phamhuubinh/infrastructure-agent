#!/usr/bin/env bash
# Lint Python source with ruff
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "[lint] ruff check ."
ruff check . 2>&1 || true
echo "[lint] Done"
