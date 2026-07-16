#!/usr/bin/env bash
# Run all Python tests with timeout and structured output
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

log_file="/tmp/orion_workflow_tests.log"

echo "[tests] Starting test run at $(date)" > "$log_file"

if timeout 600 python3 -m pytest tests/ -q --tb=short 2>&1 | tee -a "$log_file"; then
    passed_line=$(grep -E 'passed|failed' "$log_file" | tail -1)
    echo "[tests] Result: $passed_line"
    exit 0
else
    echo "[tests] FAILED"
    exit 1
fi
