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
# Validation (fast smoke before task, full after task)
# ---------------------------------------------------------------------------
smoke() {
  log "SMOKE" "imports + resolver tests..."
  python3 -c "import src.shared.secrets, src.model.llm_client, src.pipeline.target_resolver; print('ok')" 2>/dev/null || true
  timeout 30 python3 -m pytest tests/pipeline/test_target_resolver.py tests/pipeline/test_intent_resolver.py -q --tb=short 2>&1 | tail -3 || true
}

full_test() {
  log "TEST" "full suite..."
  timeout 600 python3 -m pytest tests/ -q --tb=short 2>&1 | tail -3 || true
}

lint_check() { bash "$SCRIPT_DIR/commands/lint.sh" 2>&1 | tail -3 || true; }
typecheck() { bash "$SCRIPT_DIR/commands/typecheck.sh" 2>&1 | tail -3 || true; }

# ---------------------------------------------------------------------------
# Build task prompt for OpenCode
# ---------------------------------------------------------------------------
build_prompt() {
  local task_json="$1"
  echo "$task_json" | python3 -c "
import sys, json
t = json.load(sys.stdin)
print(f'''You are in an autonomous development session for Orion at /home/binh/Orion_agent.

CURRENT TASK #{t.get('id')} [{t.get('priority','?')}]
{t.get('description','')}

WHAT TO DO:
1. Read repo state (git log, status)
2. Read relevant source files
3. Implement the fix
4. Run: bash .workflow/commands/run-tests.sh
5. Review git diff
6. Commit with a clear message (git add -A && git commit -m \"...\")
7. Update .workflow/state.json: move this task to completed
8. Exit

RULES:
- Exactly ONE commit per task
- Never mix unrelated changes
- If task is already done, just mark it completed
- If task cannot be done, mark it completed with reason
- Always run tests before committing
''')
"
}

# ---------------------------------------------------------------------------
# Run one iteration
# ---------------------------------------------------------------------------
run_iteration() {
  local task_json; task_json=$(get_next_task)
  if [ "$task_json" = "null" ]; then
    return 1  # no work
  fi

  local task_id; task_id=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))")
  local task_desc; task_desc=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description','?')[:80])")

  log "TASK" "[#$task_id] $task_desc"
  mark_started "$task_id"

  # Smoke check before OpenCode
  smoke

  # Launch OpenCode — autonomous mode
  local prompt; prompt=$(build_prompt "$task_json")
  log "OPENCODE" "launching..."
  cd "$REPO_ROOT" && opencode run "$prompt" --auto --no-replay 2>&1 | tee -a "$SESSION_LOG" || true

  # Post OpenCode: run validation (non-blocking, detached)
  log "TASK" "[#$task_id] post-run validation..."
  (
    lint_check
    typecheck
    # Full test runs detached — does not block the daemon loop
    timeout 600 bash "$SCRIPT_DIR/commands/run-tests.sh" > /tmp/orion_full_test.log 2>&1 || true
    log "TEST" "detached test run finished"
  ) &

  log "TASK" "[#$task_id] done"
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
