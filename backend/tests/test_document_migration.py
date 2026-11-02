"""Breaking legacy document migration must keep a recoverable, private snapshot."""

from __future__ import annotations

import ctypes
import os
import sqlite3
import sys
from ctypes import wintypes

import pytest

from orion.persistence.sqlite import SQLiteStore


def _legacy_documents(path, *, invalid: bool = False) -> str:
    store = SQLiteStore(path)
    session = store.create_session()
    store.close()
    nullable = "" if invalid else "NOT NULL"
    with sqlite3.connect(path) as connection:
        connection.executescript(f"""
            PRAGMA foreign_keys=OFF;
            DROP TABLE document_ingestion_events;
            DROP TABLE document_segments;
            DROP TABLE documents;
            CREATE TABLE documents (
                document_id TEXT PRIMARY KEY, attachment_id TEXT NOT NULL UNIQUE,
                session_id TEXT {nullable}, blob_id TEXT NOT NULL,
                name TEXT NOT NULL, media_type TEXT, status TEXT NOT NULL,
                normalized_text TEXT, error_message TEXT, deleted_at TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE document_segments (
                segment_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(document_id),
                ordinal INTEGER NOT NULL, text TEXT NOT NULL,
                page INTEGER, section TEXT, UNIQUE(document_id, ordinal)
            );
            CREATE TABLE document_ingestion_events (
                event_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL REFERENCES documents(document_id),
                state TEXT NOT NULL, error_message TEXT, created_at TEXT NOT NULL
            );
        """)
        connection.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "document-valid",
                "attachment-valid",
                session,
                "blob-valid",
                "name",
                "text/plain",
                "ready",
                "source text",
                None,
                None,
                "2026-01-01",
                "2026-01-01",
            ),
        )
        connection.execute(
            "INSERT INTO document_segments VALUES (?, ?, ?, ?, ?, ?)",
            ("segment-valid", "document-valid", 0, "source text", 1, None),
        )
        connection.execute(
            "INSERT INTO document_ingestion_events VALUES (?, ?, ?, ?, ?)",
            ("event-valid", "document-valid", "ready", None, "2026-01-01"),
        )
        if invalid:
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "document-invalid",
                    "attachment-invalid",
                    None,
                    "blob-invalid",
                    "bad",
                    None,
                    "ready",
                    None,
                    None,
                    None,
                    "2026-01-01",
                    "2026-01-01",
                ),
            )
    return session


def _snapshot(path):
    directories = tuple(path.parent.glob(".orion-migration-*"))
    assert len(directories) == 1
    backup = directories[0] / path.name
    assert backup.is_file()
    if os.name != "nt":
        assert directories[0].stat().st_mode & 0o077 == 0
        assert backup.stat().st_mode & 0o077 == 0
    else:
        for item in (directories[0], backup):
            acl = _windows_acl_text(item)
            assert "D:P" in acl and acl.count("(A;") == 2 and ";;;SY)" in acl
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] >= 1
    return backup


def _windows_acl_text(path) -> str:
    if sys.platform != "win32":
        raise AssertionError("Windows ACL test requires Windows")
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    advapi.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi.GetNamedSecurityInfoW.restype = wintypes.DWORD
    code = advapi.GetNamedSecurityInfoW(
        str(path), 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
    )
    assert code == 0
    string = wintypes.LPWSTR()
    try:
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL
        assert advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, 1, 4, ctypes.byref(string), None
        )
        return string.value
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        if string.value:
            kernel.LocalFree(ctypes.cast(string, ctypes.c_void_p))
        kernel.LocalFree(descriptor)


def test_legacy_document_owner_migration_keeps_children_and_private_backup(tmp_path):
    path = tmp_path / "orion.db"
    session = _legacy_documents(path)
    migrated = SQLiteStore(path)
    try:
        columns = {
            row["name"]: row["notnull"]
            for row in migrated._connection.execute("PRAGMA table_info(documents)")
        }
        assert columns["project_id"] == 0 and columns["session_id"] == 0
        assert tuple(
            migrated._connection.execute(
                "SELECT session_id, normalized_text FROM documents "
                "WHERE document_id='document-valid'"
            ).fetchone()
        ) == (session, "source text")
        assert (
            migrated._connection.execute(
                "SELECT text FROM document_segments WHERE segment_id='segment-valid'"
            ).fetchone()[0]
            == "source text"
        )
        assert (
            migrated._connection.execute(
                "SELECT state FROM document_ingestion_events WHERE event_id='event-valid'"
            ).fetchone()[0]
            == "ready"
        )
        assert migrated._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        migrated.close()
    backup = _snapshot(path)
    with sqlite3.connect(backup) as connection:
        assert "project_id" not in {
            r[1] for r in connection.execute("PRAGMA table_info(documents)")
        }
    reopened = SQLiteStore(path)
    reopened.close()
    assert tuple(tmp_path.glob(".orion-migration-*")) == (backup.parent,)


def test_failed_legacy_document_migration_rolls_back_all_table_changes(tmp_path):
    path = tmp_path / "orion.db"
    _legacy_documents(path, invalid=True)
    with pytest.raises(sqlite3.IntegrityError):
        SQLiteStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM document_segments").fetchone()[0] == 1
        assert (
            connection.execute("SELECT count(*) FROM document_ingestion_events").fetchone()[0] == 1
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='documents_new'"
            ).fetchone()
            is None
        )
        assert "project_id" not in {
            r[1] for r in connection.execute("PRAGMA table_info(documents)")
        }
    _snapshot(path)
