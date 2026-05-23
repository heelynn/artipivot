"""SQLite-backed DocumentStore — local persistent storage, zero dependencies."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from artipivot.storage.base import DocumentStore


class SQLiteDocumentStore(DocumentStore):
    """SQLite-backed document store for local development with persistence.

    Data survives process restarts. Uses Python's built-in ``sqlite3`` module.
    Thread-safe via per-thread connections and WAL journal mode.
    """

    def __init__(self, db_path: str = ".artipivot/data.db") -> None:
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = str(db_file)
        self._local = threading.local()
        self._init_db()

    # ── connection management ──

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS documents ("
            "  collection TEXT NOT NULL,"
            "  key TEXT NOT NULL,"
            "  data TEXT NOT NULL,"
            "  PRIMARY KEY (collection, key)"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_collection ON documents(collection)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notifications ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  collection TEXT NOT NULL,"
            "  key TEXT NOT NULL,"
            "  action TEXT NOT NULL,"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_collection_time "
            "ON notifications(collection, created_at)"
        )
        self._conn.commit()

    # ── DocumentStore API ──

    async def get(self, collection: str, key: str) -> dict | None:
        row = self._conn.execute(
            "SELECT data FROM documents WHERE collection = ? AND key = ?",
            (collection, key),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    async def put(self, collection: str, key: str, data: dict) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO documents (collection, key, data) "
            "VALUES (?, ?, ?)",
            (collection, key, json.dumps(data, ensure_ascii=False)),
        )
        self._conn.commit()

    async def delete(self, collection: str, key: str) -> None:
        self._conn.execute(
            "DELETE FROM documents WHERE collection = ? AND key = ?",
            (collection, key),
        )
        self._conn.commit()

    async def query(self, collection: str, filter: dict) -> list[dict]:
        if not filter:
            rows = self._conn.execute(
                "SELECT data FROM documents WHERE collection = ?",
                (collection,),
            ).fetchall()
        else:
            conditions = " AND ".join(
                f"json_extract(data, '$.{k}') = ?" for k in filter
            )
            values = [str(v) if not isinstance(v, str) else v for v in filter.values()]
            rows = self._conn.execute(
                f"SELECT data FROM documents WHERE collection = ? AND {conditions}",
                (collection, *values),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    # ── notification methods (for PollingChangeNotifier) ──

    def insert_notification(
        self, collection: str, key: str, action: str, data: dict
    ) -> None:
        """Insert a notification record for polling consumers."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO notifications (collection, key, action, data, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (collection, key, action, json.dumps(data, ensure_ascii=False), now),
        )
        self._conn.commit()

    def query_notifications(
        self, collection: str, since: str
    ) -> list[dict]:
        """Query notifications since a given ISO timestamp (exclusive)."""
        rows = self._conn.execute(
            "SELECT id, collection, key, action, data, created_at "
            "FROM notifications "
            "WHERE collection = ? AND created_at > ? "
            "ORDER BY created_at ASC",
            (collection, since),
        ).fetchall()
        return [
            {
                "id": row[0],
                "collection": row[1],
                "key": row[2],
                "action": row[3],
                "data": json.loads(row[4]),
                "created_at": row[5],
            }
            for row in rows
        ]

    def cleanup_notifications(self, retention_hours: float = 1.0) -> int:
        """Delete notifications older than retention_hours. Returns deleted count."""
        cursor = self._conn.execute(
            "DELETE FROM notifications "
            "WHERE created_at < datetime('now', ?)",
            (f"-{retention_hours} hours",),
        )
        self._conn.commit()
        return cursor.rowcount
