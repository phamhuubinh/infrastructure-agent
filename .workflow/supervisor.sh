#!/usr/bin/env bash
# =============================================================================
# Orion Autonomous Development Supervisor
# =============================================================================
# Orchestrates OpenCode sessions to continuously improve the repository.
# Usage:
#   ./.workflow/supervisor.sh              # Start new session
#   ./.workflow/supervisor.sh --resume     # Resume interrupted session
#   ./.workflow/supervisor.sh --status     # Show current state
#   ./.workflow/supervisor.sh --validate   # Run validation only
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR/..")"
STATE_FILE="$SCRIPT_DIR/state.json"
SESSION_LOG="$SCRIPT_DIR/session.log"
BACKUP_DIR="$SCRIPT_DIR/backups"

mkdir -p "$BACKUP_DIR"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

log() {
    local level="$1"; shift
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] [$level] $*"
    echo "$msg" | tee -a "$SESSION_LOG"
}

die() {
    log "FATAL" "$*"
    exit 1
}

save_state() {
    echo "$1" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

backup_state() {
    cp "$STATE_FILE" "$BACKUP_DIR/state_$(date +%Y%m%d_%H%M%S).json" 2>/dev/null || true
}

_count_tests() {
    local logfile="${1:-}"
    if [ -z "$logfile" ]; then
        echo "0 0"
        return
    fi
    local passed
    passed=$(grep -oP '\d+(?= passed)' "$logfile" | tail -1)
    local failed
    failed=$(grep -oP '\d+(?= failed)' "$logfile" | tail -1)
    echo "${passed:-0} ${failed:-0}"
}

_run_tests() {
    log "TEST" "Running full test suite..."
    bash "$SCRIPT_DIR/commands/run-tests.sh" 2>&1 | tee /tmp/orion_test_output.log || true
    local counts
    counts=$(_count_tests /tmp/orion_test_output.log)
    local passed="${counts% *}"
    local failed="${counts#* }"
    echo "$passed $failed"
}

_run_lint() {
    log "LINT" "Running linter..."
    bash "$SCRIPT_DIR/commands/lint.sh" 2>&1 || true
}

_run_typecheck() {
    log "TYPECHECK" "Running TypeScript check..."
    bash "$SCRIPT_DIR/commands/typecheck.sh" 2>&1 || true
}

_validate_all() {
    log "VALIDATE" "Running all validations..."
    _run_lint
    _run_typecheck
    local counts
    counts=$(_run_tests)
    local passed="${counts% *}"
    local failed="${counts#* }"
    echo "$passed $failed"
}

# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

read_state() {
    if [ ! -f "$STATE_FILE" ]; then
        echo '{"backlog":[],"completed":[],"session":null,"metrics":{"tests_passed":0,"tests_total":0,"commits_made":0,"last_full_test_duration_s":0}}'
        return
    fi
    cat "$STATE_FILE"
}

is_interrupted() {
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
try:
    s = json.load(sys.stdin)
    sess = s.get('session')
    if sess and sess.get('interrupted', False):
        sys.exit(0)
    sys.exit(1)
except:
    sys.exit(1)
" 2>/dev/null && return 0 || return 1
}

get_next_task() {
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
backlog = s.get('backlog', [])
pending = [t for t in backlog if t.get('status') == 'pending']
if pending:
    # Return first pending task sorted by priority
    priorities = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
    pending.sort(key=lambda t: (priorities.get(t.get('priority', 'P3'), 99), t.get('id', 999)))
    print(json.dumps(pending[0]))
else:
    print('null')
"
}

mark_started() {
    local task_id="$1"
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
for t in s.get('backlog', []):
    if t.get('id') == $task_id:
        t['status'] = 'in_progress'
        t['started_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

mark_completed() {
    local task_id="$1"
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
completed_task = None
remaining = []
for t in s.get('backlog', []):
    if t.get('id') == $task_id:
        t['status'] = 'completed'
        t['completed_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
        completed_task = t
    else:
        remaining.append(t)
s['backlog'] = remaining
if completed_task:
    s.setdefault('completed', []).append(completed_task)
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

update_metrics() {
    local passed="$1"; shift
    local total="$1"
    local commits="$2"
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
s['metrics']['tests_passed'] = $passed
s['metrics']['tests_total'] = $total
s['metrics']['commits_made'] = s['metrics'].get('commits_made', 0) + $commits
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

start_session() {
    local session_id="sess_$(date +%Y%m%d_%H%M%S)"
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
s['session'] = {
    'id': '$session_id',
    'started_at': '$(date -u +%Y-%m-%dT%H:%M:%SZ)',
    'last_task_id': None,
    'interrupted': False
}
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    log "SESSION" "Started session $session_id"
}

end_session() {
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
if s.get('session'):
    s['session']['ended_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
    s['session']['interrupted'] = False
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
    log "SESSION" "Session ended"
}

mark_interrupted() {
    local state
    state=$(read_state)
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
if s.get('session'):
    s['session']['interrupted'] = True
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
}

# ---------------------------------------------------------------------------
# OpenCode orchestration
# ---------------------------------------------------------------------------

build_task_prompt() {
    local task_json="$1"
    echo "$task_json" | python3 -c "
import sys, json
t = json.load(sys.stdin)
print(f'''You are in an autonomous development session for the Orion repository at $REPO_ROOT.

CURRENT TASK:
ID: {t.get('id')}
Priority: {t.get('priority')}
Description: {t.get('description')}
Category: {t.get('category', 'improvement')}

REQUIREMENTS:
1. Read the current repository state (git log --oneline -5, git status, git diff --stat)
2. Read any relevant documentation
3. Understand the task and implement a fix
4. Run tests after every change
5. Review your diff before committing
6. Create exactly ONE atomic commit per logical task
7. Never mix unrelated changes
8. When done, update .workflow/state.json: mark this task completed
9. If the task cannot be completed, explain why

After committing, run:
  bash .workflow/commands/run-tests.sh
  bash .workflow/commands/lint.sh
  bash .workflow/commands/typecheck.sh

Report results.
''')
"
}

run_opencode() {
    local task_prompt="$1"
    local task_id="$2"

    log "OPENCODE" "Starting OpenCode for task $task_id"

    # Set up the task prompt file
    local prompt_file="/tmp/orion_task_${task_id}.md"
    echo "$task_prompt" > "$prompt_file"

    # Run OpenCode with the task prompt
    # Capture exit code but don't stop on failure
    set +e
    opencode --input "$prompt_file" 2>&1 | tee -a "$SESSION_LOG"
    local exit_code=$?
    set -e

    if [ $exit_code -ne 0 ] && [ $exit_code -ne 130 ]; then
        log "WARN" "OpenCode exited with code $exit_code (may be normal)"
    fi

    return $exit_code
}

# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

show_status() {
    local state
    state=$(read_state)
    echo "=== Orion Workflow Status ==="
    echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
bl = s.get('backlog', [])
co = s.get('completed', [])
se = s.get('session')
me = s.get('metrics', {})
print(f'Backlog: {len(bl)} tasks')
for t in bl:
    print(f'  [{t.get(\"priority\",\"?\")}] #{t.get(\"id\",\"?\")} {t.get(\"description\",\"?\")[:80]}  [{t.get(\"status\",\"?\")}]')
print(f'Completed: {len(co)} tasks')
print(f'Session: {se.get(\"id\",\"none\") if se else \"none\"}')
print(f'Metrics: {me.get(\"tests_passed\",0)}/{me.get(\"tests_total\",0)} tests, {me.get(\"commits_made\",0)} commits')
"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

main() {
    local mode="${1:-}"

    # Ensure we're in the repo
    cd "$REPO_ROOT"

    case "$mode" in
        --status)
            show_status
            exit 0
            ;;
        --validate)
            _validate_all
            exit $?
            ;;
        --resume)
            log "MAIN" "Resuming interrupted session"
            if ! is_interrupted; then
                log "INFO" "No interrupted session found, starting fresh"
            fi
            ;;
        --help|-h)
            echo "Usage: $0 [--status|--validate|--resume|--help]"
            exit 0
            ;;
    esac

    # Validate git state
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        die "Not a git repository"
    fi

    # Check for uncommitted changes
    if [ -n "$(git status --porcelain)" ]; then
        log "WARN" "Uncommitted changes detected:"
        git status --short | head -20 | while read -r line; do log "WARN" "  $line"; done
        log "WARN" "Consider committing before starting workflow"
    fi

    # Start session
    if [ "$mode" != "--resume" ]; then
        start_session
    fi

    backup_state

    log "MAIN" "Workflow started. Repository: $REPO_ROOT"

    local max_iterations=50
    local iteration=0

    while [ $iteration -lt $max_iterations ]; do
        iteration=$((iteration + 1))
        log "MAIN" "=== Iteration $iteration ==="

        # Check for interruption (from previous session)
        if is_interrupted; then
            log "MAIN" "Previous session was interrupted. Resetting interruption flag."
            local state
            state=$(read_state)
            echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
if s.get('session'):
    s['session']['interrupted'] = False
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"
        fi

        # Run validation on current state
        log "MAIN" "Running pre-task validation..."
        _run_tests > /dev/null 2>&1 || true
        _run_lint > /dev/null 2>&1 || true

        # Get next task
        local task_json
        task_json=$(get_next_task)

        if [ "$task_json" = "null" ] || [ -z "$task_json" ]; then
            log "MAIN" "No pending tasks. Running final validation..."
            local counts
            counts=$(_validate_all)
            local p="${counts% *}"
            local f="${counts#* }"
            update_metrics "$p" "$((p + f))" 0
            show_status
            log "MAIN" "Workflow complete. No remaining tasks."
            end_session
            exit 0
        fi

        local task_id
        task_id=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', '?'))")
        local task_desc
        task_desc=$(echo "$task_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('description', '?')[:60])")

        log "TASK" "Starting task #$task_id: $task_desc"
        mark_started "$task_id"

        # Build the prompt for OpenCode
        local prompt
        prompt=$(build_task_prompt "$task_json")

        # Run OpenCode
        set +e
        run_opencode "$prompt" "$task_id"
        local oc_exit=$?
        set -e

        # Check if OpenCode completed or was interrupted
        if [ $oc_exit -eq 130 ] || [ $oc_exit -eq 2 ]; then
            log "WARN" "OpenCode interrupted (Ctrl+C or SIGINT)"
            mark_interrupted
            log "MAIN" "Session interrupted. Resume with: $0 --resume"
            exit 130
        fi

        # Run validation
        log "MAIN" "Running post-task validation..."
        local counts
        counts=$(_run_tests)
        local passed="${counts% *}"
        local failed="${counts#* }"

        # Count new commits
        local commits_before
        commits_before=$(git rev-list --count HEAD 2>/dev/null || echo "0")

        # Update metrics
        update_metrics "$passed" "$((passed + failed))" 0

        # Check if the task was completed (state file should reflect this)
        local remaining
        remaining=$(get_next_task)
        if [ "$remaining" = "null" ] || [ -z "$remaining" ]; then
            log "TASK" "Task #$task_id completed (no remaining tasks in backlog)"
        else
            local next_id
            next_id=$(echo "$remaining" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', '?'))")
            if [ "$next_id" != "$task_id" ]; then
                log "TASK" "Task #$task_id completed (moved to next task #$next_id)"
            else
                log "WARN" "Task #$task_id may not be fully completed yet"
            fi
        fi

        # Update session state
        local state
        state=$(read_state)
        echo "$state" | python3 -c "
import sys, json
s = json.load(sys.stdin)
if s.get('session'):
    s['session']['last_task_id'] = $task_id
    s['session']['updated_at'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
print(json.dumps(s))
" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

        backup_state

        # Brief pause before next iteration
        sleep 1
    done

    log "MAIN" "Reached maximum iterations ($max_iterations). Ending."
    mark_interrupted
    show_status
    end_session
    exit 0
}

# Run main
main "$@"
