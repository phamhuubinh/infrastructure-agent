from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from src.backend import db


class _Connection:
    def __init__(self, *, rollback_fails: bool = False) -> None:
        self.closed = False
        self.rollback_fails = rollback_fails
        self.rollback_calls = 0
        self.close_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1
        if self.rollback_fails:
            raise RuntimeError("transaction is unrecoverable")

    def close(self) -> None:
        self.closed = True
        self.close_calls += 1


@pytest.fixture(autouse=True)
def _isolated_pool(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(db, "_pool_connections", [])
    monkeypatch.setattr(db, "_pool_semaphore", threading.Semaphore(1))
    monkeypatch.setattr(db, "_MAX_POOL_SIZE", 1)
    yield


def test_connection_creation_failure_returns_acquired_pool_permit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = SimpleNamespace()
    monkeypatch.setattr(db, "_import_driver", lambda: (driver, None))
    monkeypatch.setattr(
        db,
        "_connect_with_retry",
        lambda _driver, _dsn: (_ for _ in ()).throw(RuntimeError("down")),
    )

    with pytest.raises(RuntimeError, match="down"):
        db._get_conn("postgresql://example")

    # A second call reaches connection creation instead of timing out because
    # the failed first connection did not leak the only pool permit.
    monkeypatch.setattr(db, "_connect_with_retry", lambda _driver, _dsn: _Connection())
    assert isinstance(db._get_conn("postgresql://example"), _Connection)


def test_poisoned_connection_is_discarded_instead_of_requeued() -> None:
    connection = _Connection(rollback_fails=True)

    db._put_conn(connection)

    assert connection.close_calls == 1
    assert db._pool_connections == []
