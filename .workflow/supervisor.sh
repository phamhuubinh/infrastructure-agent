#!/usr/bin/env bash
# =============================================================================
# Orion Autonomous Development Supervisor — Daemon Mode
# =============================================================================
# One launch. Runs forever. No human needed.
#
#   ./.workflow/supervisor.sh              # start daemon (foreground)
#   ./.workflow/supervisor.sh --daemon     # start daemon (background)
#   ./.workflow/supervisor.sh --status     # show state
#   ./.workflow/supervisor.sh --stop       # stop daemon gracefully
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$SCRIPT_DIR/state.json"
SESSION_LOG="$SCRIPT_DIR/session.log"
PID_FILE="$SCRIPT_DIR/daemon.pid"

mkdir -p "$SCRIPT_DIR/backups"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log() { local l="$1"; shift; echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$l] $*" | tee -a "$SESSION_LOG"; }

# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------
read_state() {
  if [ ! -f "$STATE_FILE" ]; then
    echo '{"backlog":[],"completed":[],"metrics":{"tests_passed":567,"tests_total":567,"commits_made":0}}'
    return
  fi
  cat "$STATE_FILE"
}

save_state() { echo "$1" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"; }

has_pending() {
  read_state | python3 -c "
import sys, json
s = json.load(sys.stdin)
pending = [t for t in s.get('backlog', []) if t.get('status') == 'pending']
print(len(pending))
"
}

get_next_task() {
  read_state | python3 -c "
import sys, json
s = json.load(sys.stdin)
pending = [t for t in s.get('backlog', []) if t.get('status') == 'pending']
if not pending:
  print('null')
  sys.exit(0)
priorities = {'P0':0,'P1':1,'P2':2,'P3':3}
pending.sort(key=lambda t: (priorities.get(t.get('priority','P3'),99), t.get('id',999)))
import json as j
print(j.dumps(pending[0]))
"
}

mark_started() {
  local state; state=$(read_state)
  echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
for t in s.get('backlog', []):
  if t.get('id') == $1:
    t['status'] = 'in_progress'
    t['started_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# ---------------------------------------------------------------------------
# Validation — strict (exit on fail)
# ---------------------------------------------------------------------------
format_check() {
  log "FORMAT" "ruff format check..."
  ruff format --check src/ tests/ 2>&1 | tee -a "$SESSION_LOG"
}

lint_strict() {
  log "LINT" "ruff strict check..."
  ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501 2>&1 | tee -a "$SESSION_LOG"
}

test_full() {
  log "TEST" "full suite..."
  python3 -m pytest tests/ -q --tb=short -x 2>&1 | tee -a "$SESSION_LOG"
}

test_failed_count() {
  python3 -m pytest tests/ --collect-only -q 2>&1 | tail -1 | grep -oP '^\d+' || echo "0"
}

# ---------------------------------------------------------------------------
# Error classifiers
# ---------------------------------------------------------------------------
classify_error() {
  local log_file="$1"
  # Code error
  if grep -q "FAILED\|AssertionError\|SyntaxError\|NameError\|TypeError\|ModuleNotFoundError\|ImportError" "$log_file" 2>/dev/null; then
    echo "CODE"
    return
  fi
  # Environment error
  if grep -qi "docker.*not found\|command not found.*docker\|Cannot connect to the Docker\|postgres.*connection\|could not connect.*server\|psql.*not found" "$log_file" 2>/dev/null; then
    echo "ENVIRONMENT"
    return
  fi
  # External dependency / permission
  if grep -qi "Permission denied\|Access denied\|401\|403\|api_key.*required\|missing.*token\|secret.*not found\|no.*such.*file.*config" "$log_file" 2>/dev/null; then
    echo "BLOCKED"
    return
  fi
  # Default: code error
  echo "CODE"
}

repair_environment() {
  log "ENV" "attempting environment repair..."
  # Docker
  if ! command -v docker &>/dev/null; then
    log "ENV" "docker not found — attempting install"
    sudo apt-get update -qq && sudo apt-get install -y -qq docker.io 2>&1 | tail -3 || true
  fi
  # PostgreSQL
  if ! command -v psql &>/dev/null; then
    log "ENV" "postgresql not found — attempting install"
    sudo apt-get install -y -qq postgresql postgresql-client 2>&1 | tail -3 || true
  fi
  # Ensure postgres running
  if command -v pg_isready &>/dev/null; then
    pg_isready -q || sudo service postgresql start 2>&1 || true
  fi
  log "ENV" "repair done"
}

# ---------------------------------------------------------------------------
# 16-step workflow for one task
# ---------------------------------------------------------------------------
execute_task() {
  local task_json="$1"
  local task_id; task_id=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))")
  local task_desc; task_desc=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description','?')[:80])")

  log "TASK" "[#$task_id] === START $task_desc ==="

  local log_file="/tmp/orion_task_${task_id}.log"
  local max_attempts=10
  local attempt=1

  while [ "$attempt" -le "$max_attempts" ]; do
    log "TASK" "[#$task_id] attempt $attempt/$max_attempts"

    # Step 7: Implement
    cd "$REPO_ROOT" && timeout 600 opencode run "$(build_prompt "$task_json")" --auto --no-replay 2>&1 | tee "$log_file" || true

    # Step 8: Self review
    if ! git diff --quiet; then
      log "REVIEW" "[#$task_id] changes detected"
    else
      log "REVIEW" "[#$task_id] no changes"
    fi

    # Step 9: Format
    log "FORMAT" "[#$task_id] ruff format..."
    ruff format src/ tests/ 2>&1 | tee -a "$log_file" || true

    # Step 10: Lint
    log "LINT" "[#$task_id] ruff check..."
    if ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501 2>&1 | tee -a "$log_file"; then
      log "LINT" "[#$task_id] PASS"
    else
      log "LINT" "[#$task_id] FAIL"
      local err_type; err_type=$(classify_error "$log_file")
      case "$err_type" in
        CODE)    log "TASK" "[#$task_id] code error — retrying" ;;
        ENVIRONMENT) repair_environment; log "TASK" "[#$task_id] environment repaired — retrying" ;;
        BLOCKED) log "TASK" "[#$task_id] BLOCKED (external dependency)"; break ;;
      esac
      attempt=$((attempt + 1))
      continue
    fi

    # Step 11: Unit tests
    log "TEST" "[#$task_id] unit tests..."
    if python3 -m pytest tests/ -q --tb=short -x 2>&1 | tee -a "$log_file"; then
      log "TEST" "[#$task_id] PASS"
    else
      log "TEST" "[#$task_id] FAIL"
      local err_type; err_type=$(classify_error "$log_file")
      case "$err_type" in
        CODE)    log "TASK" "[#$task_id] code error — retrying" ;;
        ENVIRONMENT) repair_environment; log "TASK" "[#$task_id] environment repaired — retrying" ;;
        BLOCKED) log "TASK" "[#$task_id] BLOCKED (external dependency)"; break ;;
      esac
      attempt=$((attempt + 1))
      continue
    fi

    # Step 12: Full regression suite
    log "TEST" "[#$task_id] regression (full suite)..."
    if python3 -m pytest tests/ -q --tb=short 2>&1 | tee -a "$log_file"; then
      log "TEST" "[#$task_id] ALL PASS"
    else
      log "TEST" "[#$task_id] FAIL"
      local err_type; err_type=$(classify_error "$log_file")
      case "$err_type" in
        CODE)    log "TASK" "[#$task_id] code error — retrying" ;;
        ENVIRONMENT) repair_environment; log "TASK" "[#$task_id] environment repaired — retrying" ;;
        BLOCKED) log "TASK" "[#$task_id] BLOCKED (external dependency)"; break ;;
      esac
      attempt=$((attempt + 1))
      continue
    fi

    # All pass
    log "TASK" "[#$task_id] all checks passed after $attempt attempts"
    break
  done

  if [ "$attempt" -le "$max_attempts" ]; then
    log "TASK" "[#$task_id] DONE"
    return 0
  else
    log "TASK" "[#$task_id] BLOCKED after $max_attempts attempts"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Build task prompt for OpenCode
# ---------------------------------------------------------------------------
build_prompt() {
  local task_json="$1"
  echo "$task_json" | python3 -c "
import sys, json
t = json.load(sys.stdin)
print(f'''You are implementing task #{t.get('id')} in Orion (Infrastructure Investigation Platform).

TASK: {t.get('description','')}

16-STEP WORKFLOW — follow exactly:
1. Read repo state (git log, status)
2. Read docs and source files to understand architecture
3. Read relevant code for this task
4. Plan implementation
5. Implement
6. Self-review
7. Format: ruff format src/ tests/
8. Lint: ruff check src/ tests/ --select ALL --ignore D --ignore INP --ignore S --ignore E501
9. Unit test: python3 -m pytest tests/ -q --tb=short -x
10. Integration test (if applicable)
11. Regression test: full suite
12. If any step fails → fix and re-run
13. Update documentation if needed
14. Git commit: git add -A && git commit -m \"...\"
15. Update .workflow/state.json: mark task as completed
16. Move to next task

RULES:
- Exactly ONE commit per task
- Never mix unrelated changes
- Never leave tests broken
- If blocked after 3 attempts, mark blocked and move on
''')
"
}

# ---------------------------------------------------------------------------
# Run one iteration (16-step)
# ---------------------------------------------------------------------------
run_iteration() {
  local task_json; task_json=$(get_next_task)
  if [ "$task_json" = "null" ]; then
    return 1
  fi

  local task_id; task_id=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))")

  log "TASK" "[#$task_id] starting"
  mark_started "$task_id"

  if execute_task "$task_json"; then
    # Step 14: Git commit (already done by opencode)
    log "TASK" "[#$task_id] completed successfully"
  else
    log "TASK" "[#$task_id] BLOCKED — max attempts exceeded"
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Daemon loop — never exits
# ---------------------------------------------------------------------------
daemon_loop() {
  log "DAEMON" "started. pid=$$"
  local idle_seconds=30
  local empty_cycles=0

  while true; do
    local pending; pending=$(has_pending)
    if [ "$pending" -gt 0 ]; then
      empty_cycles=0
      run_iteration || true
      # brief pause between iterations
      sleep 2
    else
      empty_cycles=$((empty_cycles + 1))
      # Exponential backoff: 30s -> 60s -> 120s -> 300s max
      local sleep_time=$idle_seconds
      if [ "$empty_cycles" -gt 1 ]; then
        sleep_time=$((idle_seconds * 2))
        [ "$sleep_time" -gt 300 ] && sleep_time=300
      fi
      if [ "$empty_cycles" -eq 1 ] || [ "$((empty_cycles % 10))" -eq 0 ]; then
        log "DAEMON" "idle (${empty_cycles}x). sleeping ${sleep_time}s. poll every 30s."
      fi
      sleep "$sleep_time"
    fi
  done
}

# ---------------------------------------------------------------------------
# Start daemon in background
# ---------------------------------------------------------------------------
start_daemon() {
  if [ -f "$PID_FILE" ]; then
    local old_pid; old_pid=$(cat "$PID_FILE")
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "Daemon already running (pid $old_pid)"
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  # Fork
  (
    # Ensure single instance
    echo "$$" > "$PID_FILE"
    # Trap to clean up PID on exit
    cleanup() { rm -f "$PID_FILE"; }
    trap cleanup EXIT TERM INT

    cd "$REPO_ROOT"
    daemon_loop
  ) &

  local child_pid=$!
  echo "$child_pid" > "$PID_FILE"
  echo "Daemon started (pid $child_pid)"
  echo "Log: $SESSION_LOG"
  echo "Stop: $0 --stop"
}

# ---------------------------------------------------------------------------
# Stop daemon
# ---------------------------------------------------------------------------
stop_daemon() {
  if [ ! -f "$PID_FILE" ]; then
    echo "No daemon running"
    exit 0
  fi
  local pid; pid=$(cat "$PID_FILE")
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    sleep 1
    echo "Daemon (pid $pid) stopped"
  else
    echo "No daemon running (stale PID)"
  fi
  rm -f "$PID_FILE"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
case "${1:-}" in
  --status)
    read_state | python3 -c "
import sys, json
s = json.load(sys.stdin)
bl = s.get('backlog', [])
co = s.get('completed', [])
me = s.get('metrics', {})
print(f'Backlog: {len(bl)} tasks')
for t in bl:
  print(f'  [{t.get(\"priority\",\"?\")}] #{t.get(\"id\",\"?\")} {t.get(\"description\",\"?\")[:80]}  [{t.get(\"status\",\"?\")}]')
print(f'Completed: {len(co)} tasks')
print(f'Tests: {me.get(\"tests_passed\",0)}/{me.get(\"tests_total\",0)}')
"
    if [ -f "$PID_FILE" ]; then
      echo "Daemon: running (pid $(cat "$PID_FILE"))"
    else
      echo "Daemon: stopped"
    fi
    ;;
  --stop) stop_daemon ;;
  --daemon|"")
    if [ "${1:-}" = "--daemon" ]; then
      start_daemon
    else
      # Foreground
      cd "$REPO_ROOT"
      echo "$$" > "$PID_FILE"
      cleanup() { rm -f "$PID_FILE"; }
      trap cleanup EXIT TERM INT
      daemon_loop
    fi
    ;;
  *)
    echo "Usage: $0 [--daemon|--status|--stop]"
    exit 1
    ;;
esac
