# Task 011: SQLite as Default Persistence (Replace JSON Files)

> **Source:** IMPLEMENTATION_BACKLOG.md, Item 11 (Sprint 3, P3 - Future)
> **Created:** 2026-07-26
> **Status:** pending

---

## 1. Problem Summary

Orion has two persistence backends: JSON files (default, zero-config) and PostgreSQL (optional, multi-instance). JSON files lack:
- Concurrency safety (no WAL, no locking beyond `threading.RLock`)
- Query capability (no search across sessions, no filtering)
- Migration support (schema changes require manual JSON transformation)

Replace JSON files with SQLite, reducing backends from 2 to 1 for single-user deployments. PostgreSQL remains for multi-instance. This decreases maintenance, not increases it.

---

## 2. Files to Modify

| # | File | Change | LOC Impact |
|---|------|--------|------------|
| 1 | `src/backend/sqlite_store.py` (NEW) | `SQLiteConversationStore` implementing same interface as PostgreSQL store | ~200 lines |
| 2 | `src/agent/conversation_store.py` | Interface refinement for backend-agnostic API | ~20 lines modified |
| 3 | `src/backend/db.py` | Shared migration infrastructure (Alembic) | ~30 lines modified |
| 4 | `config/servers.json` | Storage backend selection (`orion_storage_backend`) | ~3 lines |
| 5 | `src/backend/app.py` | Use SQLite store when no `ORION_DATABASE_URL` | ~10 lines modified |

**Total estimated change:** ~263 lines

---

## 3. Detailed Instructions

### 3.1 `SQLiteConversationStore` (NEW)

```python
import sqlite3
import threading
import json
from pathlib import Path

class SQLiteConversationStore:
    """SQLite-backed conversation store replacing JSON files.
    
    Features:
    - WAL mode for concurrent read/write
    - FTS5 full-text search across sessions
    - Alembic migrations (shared with PostgreSQL where possible)
    - Zero-config (no external daemon)
    """
    
    def __init__(self, db_path: Path = Path("~/.orion/sessions.db")):
        self._db_path = db_path.expanduser()
        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
    
    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._run_migrations()
        return self._conn
    
    def create_session(self, source: str = "api") -> str:
        ...
    
    def get_session(self, session_id: str) -> dict | None:
        ...
    
    def list_sessions(self) -> list[dict]:
        ...
    
    def search_sessions(self, query: str) -> list[dict]:
        """FTS5 full-text search across sessions."""
        ...
    
    def add_turn(self, session_id: str, turn: dict) -> None:
        ...
    
    def _run_migrations(self):
        """Alembic migrations, shared with PostgreSQL where possible."""
        ...
```

### 3.2 Migration from JSON

```python
def migrate_json_to_sqlite(json_path: Path, sqlite_store: SQLiteConversationStore):
    """One-time import of existing JSON sessions into SQLite."""
    for json_file in json_path.glob("*.json"):
        data = json.loads(json_file.read_text())
        sqlite_store._import_session(data)
```

### 3.3 Config

```json
// servers.json addition:
{
  "storage": {
    "backend": "sqlite",     // "sqlite" | "postgresql"
    "sqlite_path": "~/.orion/sessions.db"
  }
}
```

---

## 4. Dependencies

- **Task #003** (Unified Config) — storage backend selection through unified config

---

## 5. Verification Criteria

- [ ] Session write/read latency <10% increase vs. JSON
- [ ] FTS5 search returns correct results
- [ ] WAL mode concurrent access works (multiple readers + writer)
- [ ] JSON-to-SQLite migration success for existing sessions
- [ ] Existing `PostgresConversationStore` path unchanged
- [ ] Tests pass: `python -m pytest tests/ -q --tb=short -x -k "not slow"`
- [ ] One atomic commit: `feat: add SQLite conversation store replacing JSON as default`