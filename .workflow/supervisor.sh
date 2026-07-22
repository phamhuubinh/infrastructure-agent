#!/usr/bin/env bash
# =============================================================================
# Orion Autonomous Development Supervisor
# =============================================================================
# Pick task → codex exec với DeepSeek-V4-Flash.
# Nếu codex không available → fallback self-exec (format+lint+test).
#
# Usage:
#   ./.workflow/supervisor.sh              # foreground
#   ./.workflow/supervisor.sh --daemon     # background
#   ./.workflow/supervisor.sh --status     # show backlog
#   ./.workflow/supervisor.sh --stop       # kill daemon
# =============================================================================

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$SCRIPT_DIR/state.json"
SESSION_LOG="$SCRIPT_DIR/session.log"
PID_FILE="$SCRIPT_DIR/daemon.pid"
TASK_LOG_DIR="$SCRIPT_DIR/task_logs"
BACKUP_DIR="$SCRIPT_DIR/backups"
MAX_RETRIES=2

mkdir -p "$BACKUP_DIR" "$TASK_LOG_DIR"

log() { local l="$1"; shift; echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$l] $*" | tee -a "$SESSION_LOG"; }
read_state() { cat "$STATE_FILE" 2>/dev/null || echo '{"backlog":[],"completed":[],"metrics":{}}'; }
save_state() { local t; t=$(mktemp /tmp/orion_state_XXXX.json); echo "$1" > "$t" && mv "$t" "$STATE_FILE"; }

in_progress_count() { read_state | python3 -c "import sys,json; s=json.load(sys.stdin); print(len([t for t in s.get('backlog',[]) if t.get('status')=='in_progress']))"; }
has_codex() { command -v codex &>/dev/null; }

get_next_task() {
  read_state | python3 -c "
import sys,json; s=json.load(sys.stdin)
p=[t for t in s.get('backlog',[]) if t.get('status')=='pending']
if not p: print('null'); sys.exit(0)
p.sort(key=lambda t:({'P0':0,'P1':1,'P2':2,'P3':99}.get(t.get('priority','P3'),99),t.get('phase','99'),t.get('id',999)))
print(json.dumps(p[0]))"
}

mark_started() {
  local tid=$1 n; n=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  save_state "$(read_state | python3 -c "import sys,json; s=json.load(sys.stdin)
for t in s.get('backlog',[]):
  if t.get('id')==$tid: t['status']='in_progress'; t['started_at']='$n'
print(json.dumps(s))")"
}

mark_done() {
  local tid=$1
  save_state "$(read_state | python3 -c "
import sys,json; s=json.load(sys.stdin)
entry=None; remaining=[]
for t in s.get('backlog',[]):
  if t.get('id')==$tid: t['status']='completed'; entry=t
  else: remaining.append(t)
if entry:
  s.setdefault('completed',[]).append({'id':entry['id'],'status':'completed','title':entry.get('title','')})
s['backlog']=remaining
s['metrics']['commits_made']=s['metrics'].get('commits_made',0)+1
print(json.dumps(s))")"
}

mark_blocked() {
  local tid=$1 n; n=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  save_state "$(read_state | python3 -c "import sys,json; s=json.load(sys.stdin)
for t in s.get('backlog',[]):
  if t.get('id')==$tid: t['status']='blocked'; t['blocked_at']='$n'
print(json.dumps(s))")"
}

deps_met() {
  local tid=$1
  read_state | python3 -c "
import sys,json; s=json.load(sys.stdin)
t=next((x for x in s['backlog'] if x.get('id')==$tid),None)
if not t: print('false'); sys.exit(0)
done=[x.get('id') for x in s.get('completed',[])]
for d in t.get('depends_on',[]):
  if d not in done:
    dt=next((x for x in s['backlog'] if x.get('id')==d),None)
    if dt and dt.get('status')=='completed': continue
    print('false'); sys.exit(0)
print('true')"
}

# --- Codex executor ---
codex_exec_task() {
  local tid=$1 lf=$2 pf=$3
  log "EXEC" "[#$tid] codex exec (DeepSeek-V4-Flash, sv1)"
  CODEX_MODEL=sv1 timeout 900 codex exec --dangerously-bypass-approvals-and-sandbox < "$pf" 2>&1 | tee "$lf"
  grep -q "TASK_COMPLETE" "$lf" 2>/dev/null
}

# --- Self-exec fallback (khi không có codex) ---
self_exec_task() {
  local tid=$1 lf=$2
  log "EXEC" "[#$tid] self-exec (format → lint → test)"
  python3 -c "
import subprocess, os
os.chdir('$REPO_ROOT')
print('[1/3] ruff format...', flush=True); subprocess.run(['ruff','format','src/','tests/'], capture_output=True)
print('[2/3] ruff check...', flush=True)
r=subprocess.run(['ruff','check','src/','tests/'], capture_output=True,text=True)
if r.returncode==0: print('lint OK', flush=True)
else: print(r.stdout[-500:]); print(r.stderr[-500:]); print('LINT_FAILED',flush=True)
print('[3/3] pytest...', flush=True)
try:
  p=subprocess.run(['python3','-m','pytest','tests/','-q','--tb=short','-x','-k','not slow'], capture_output=True,text=True,timeout=120)
  print(p.stdout[-2000:])
  if p.stderr: print(p.stderr[-1000:])
  if p.returncode==0: print('TASK_COMPLETE',flush=True)
  else: print('TEST_FAILED',flush=True)
except subprocess.TimeoutExpired: print('TIMEOUT',flush=True)
" 2>&1 | tee "$lf"
  grep -q "TASK_COMPLETE" "$lf" 2>/dev/null
}

execute_task() {
  local tj="$1"
  local tid desc title files_f phase pri approach ac ts lf pf
  tid=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  desc=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description',''))")
  title=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('title',''))")
  files_f=$(echo "$tj" | python3 -c "import sys,json; print(' '.join(json.load(sys.stdin).get('files',[])))" 2>/dev/null || echo "")
  phase=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('phase','?'))")
  pri=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('priority','?'))")
  approach=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('approach',''))")
  ac=$(echo "$tj" | python3 -c "import sys,json; a=json.load(sys.stdin).get('acceptance_criteria',[]); print('\n'.join(f'{i+1}. {x}' for i,x in enumerate(a)))")

  ts=$(date +%Y%m%d_%H%M%S)
  lf="$TASK_LOG_DIR/task_${tid}_${ts}.log"
  log "TASK" "[#$tid] [$pri] Phase $phase $title"

  # Backup state
  cp "$STATE_FILE" "$BACKUP_DIR/state_$(date +%Y%m%d_%H%M%S).json" 2>/dev/null || true
  ls -t "$BACKUP_DIR"/state_*.json 2>/dev/null | tail -n +21 | xargs rm -f 2>/dev/null || true

  # Detect executor
  local mode="self"
  if has_codex; then mode="codex"; fi
  log "TASK" "[#$tid] executor=$mode"

  # Build prompt for codex mode
  pf=$(mktemp /tmp/orion_task_XXXX.md)
  cat > "$pf" << EOM
# Task #$tid: $title

**Priority:** $pri | **Phase:** $phase
**Files:** $files_f

## Description
$desc

## Approach
$approach

## Acceptance Criteria
$ac

## Rules
1. Read docs/ai/00_BOOTSTRAP.md first
2. Make minimal changes — DON'T refactor unrelated code
3. Run: ruff format src/ tests/ && ruff check src/ tests/
4. Run: python -m pytest tests/ -q --tb=short -x -k "not slow" — ALL must pass
5. If tests fail, FIX YOUR CODE
6. When all pass, output exactly: TASK_COMPLETE
EOM

  local a=1 m=$((MAX_RETRIES + 1))
  while [ "$a" -le "$m" ]; do
    if [ "$mode" = "codex" ]; then
      if codex_exec_task "$tid" "$lf" "$pf"; then
        log "TASK" "[#$tid] done via codex exec attempt $a"
        mark_done "$tid"; rm -f "$pf"; return 0
      fi
    else
      if self_exec_task "$tid" "$lf"; then
        log "TASK" "[#$tid] done via self-exec attempt $a"
        mark_done "$tid"; rm -f "$pf"; return 0
      fi
    fi
    a=$((a+1)); [ "$a" -le "$m" ] && sleep 3
  done

  log "TASK" "[#$tid] BLOCKED after $m attempts"
  mark_blocked "$tid"; rm -f "$pf"; return 1
}

run_iteration() {
  if [ "$(in_progress_count)" -gt 0 ]; then return 1; fi
  local tj; tj=$(get_next_task); [ "$tj" = "null" ] && return 1
  local tid; tid=$(echo "$tj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','?'))")
  if ! deps_met "$tid"; then log "DEPS" "[#$tid] dep not met"; return 1; fi
  mark_started "$tid"; execute_task "$tj"
}

daemon_loop() {
  log "DAEMON" "started pid=$$"
  local idle=30 ec=0
  while true; do
    if [ "$(in_progress_count)" -gt 0 ]; then ec=0; sleep 5; continue; fi
    if [ "$(python3 -c "import sys,json; s=json.load(open('$STATE_FILE')); print(len([t for t in s.get('backlog',[]) if t.get('status')=='pending']))")" -gt 0 ]; then
      ec=0; run_iteration || true; sleep 2
    else
      ec=$((ec+1)); local s=$idle; [ "$ec" -gt 1 ] && s=$((idle*2)); [ "$s" -gt 300 ] && s=300
      [ $((ec%5)) -eq 1 ] && log "DAEMON" "idle ${ec}x sleep ${s}s"
      sleep "$s"
    fi
  done
}

start_daemon() {
  if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then echo "Already running pid $(cat "$PID_FILE")"; exit 0; fi
  rm -f "$PID_FILE"
  cd "$REPO_ROOT" && nohup "$0" > "$SESSION_LOG" 2>&1 &
  echo "$!" > "$PID_FILE"
  echo "Supervisor started pid $(cat "$PID_FILE")"
  echo "  Status: ./.workflow/supervisor.sh --status"
  echo "  Stop:   ./.workflow/supervisor.sh --stop"
}

stop_daemon() {
  [ ! -f "$PID_FILE" ] && echo "No daemon" && exit 0
  local p=$(cat "$PID_FILE")
  kill "$p" 2>/dev/null && echo "Stopping pid $p" || true
  for i in 1 2 3; do sleep 1; kill -0 "$p" 2>/dev/null || { rm -f "$PID_FILE"; echo "Stopped"; exit 0; }; done
  kill -9 "$p" 2>/dev/null || true; rm -f "$PID_FILE"; echo "Force killed"
}

case "${1:-}" in
  --status)
    echo "=== Orion Supervisor Status ==="
    if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then echo "Daemon: running pid $(cat "$PID_FILE")"; else echo "Daemon: stopped"; fi
    echo ""
    read_state | python3 -c "
import sys,json; s=json.load(sys.stdin)
b=s.get('backlog',[]); c=s.get('completed',[]); m=s.get('metrics',{})
print(f'Backlog: {len(b)} | Completed: {len(c)} | Commits: {m.get(\"commits_made\",0)}')
print()
for t in sorted(b, key=lambda x: ({'P0':0,'P1':1,'P2':2,'P3':99}.get(x.get('priority','P3'),99),x.get('phase','99'),x.get('id',999))):
  d=t.get('depends_on',[]); ds=f' dep:{d}' if d else ''
  print(f'  [{t[\"phase\"]}][{t[\"priority\"]}] #{t[\"id\"]:>3} {t[\"title\"][:55]:<55} [{t[\"status\"]:>12}]{ds}')
    "
    echo "Model: DeepSeek-V4-Flash (sv1) via codex exec"
    if has_codex; then echo "Executor: codex"; else echo "Executor: self-exec (no codex)"; fi
    ;;
  --stop) stop_daemon ;;
  --daemon) start_daemon ;;
  "")
    cd "$REPO_ROOT"
    log "INIT" "supervisor started (foreground)"
    echo "$$" > "$PID_FILE"; trap 'rm -f "$PID_FILE"' EXIT TERM INT
    daemon_loop
    ;;
  *) echo "Usage: $0 [--daemon|--status|--stop]" && exit 1 ;;
esac
