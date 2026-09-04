"""SQLite-backed session storage for MogBot.

Replaces MogBotFloorManager's in-memory session dict so a server restart
doesn't wipe in-progress interviews. See ACTION_PLAN.md Milestone 9.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Optional


class SQLiteSessionStore:
    """Thread-safe session storage backed by a SQLite file.

    Each session record (state, questions, current_index, max_questions) is
    stored as an opaque JSON blob keyed by session_id - the simplest
    persistence that works without redesigning the record shape into
    relational columns, matching ACTION_PLAN.md's "SQLite (simplest)" call.

    `db_path` defaults to `MOGBOT_SESSIONS_DB` (or `data/sessions.db`) so a
    deployment can point it at a mounted persistent volume.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = Path(db_path or os.environ.get("MOGBOT_SESSIONS_DB", "data/sessions.db"))
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_schema(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        record_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT record_json FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, session_id: str, record: Dict[str, Any]) -> None:
        record_json = json.dumps(record)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, record_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        record_json = excluded.record_json,
                        updated_at = excluded.updated_at
                    """,
                    (session_id, record_json, now),
                )
                conn.commit()
            finally:
                conn.close()

    def delete(self, session_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
            finally:
                conn.close()
