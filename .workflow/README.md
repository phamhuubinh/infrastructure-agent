# Autonomous Development Workflow

This directory contains the autonomous development supervisor for Orion.

## Architecture

```
workflow/
├── supervisor.sh       # Entry point — orchestrates the entire workflow
├── state.json          # Persistent backlog & session state
├── session.log         # Structured log of all iterations
├── commands/           # Reusable task command files
│   ├── run-tests.sh
│   ├── lint.sh
│   ├── typecheck.sh
│   └── benchmark.sh
└── README.md
```

## How It Works

1. `supervisor.sh` is the entry point. It starts OpenCode with task context.
2. After each OpenCode session, the supervisor resumes, reads `state.json`, and either:
   - Starts the next task from the backlog, OR
   - Restarts if the previous session was interrupted
3. Each task produces:
   - A git commit (atomic, one per logical change)
   - Test results
   - Lint + typecheck results
   - Updated `state.json` with progress
4. When backlog is empty, the supervisor runs validation and exits.

## Usage

```bash
# Start the workflow
./.workflow/supervisor.sh
```

## state.json Format

```json
{
  "backlog": [
    {"id": 1, "priority": "P0", "description": "...", "status": "pending"},
    {"id": 2, "priority": "P1", "description": "...", "status": "pending"}
  ],
  "session": {
    "id": "sess_20240716_123456",
    "started_at": "...",
    "last_task_id": 1,
    "interrupted": false
  },
  "metrics": {
    "tests_passed": 567,
    "tests_total": 567,
    "commits_made": 0
  }
}
```
