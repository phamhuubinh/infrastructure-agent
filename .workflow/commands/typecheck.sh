#!/usr/bin/env bash
# Type-check frontend with TypeScript
set -euo pipefail

cd "$(git rev-parse --show-toplevel)/ui"

echo "[typecheck] Running tsc --noEmit..."
if npx tsc --noEmit 2>&1; then
    echo "[typecheck] PASS"
    exit 0
else
    echo "[typecheck] FAILED"
    exit 1
fi
