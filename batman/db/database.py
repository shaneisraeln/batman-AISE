"""Database backend abstraction.

Chooses a backend from a connection URL:
  - sqlite:///path/to.db   or a bare path        -> SQLite (stdlib)
  - postgresql://user:pw@host:port/db            -> PostgreSQL (psycopg)

Both backends expose the same small surface: ``execute``, ``query``,
``query_one``, and a thread-safe lock. Query strings use ``?`` placeholders;
for PostgreSQL they are translated to ``%s`` automatically, so callers write one
SQL dialect.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Iterable

DEFAULT_URL = "sqlite:///batman.db"


def _is_postgres(url: str) -> bool:
    return url.startswith("postgres://") or url.startswith("postgresql://")


class Database:
    """Minimal cross-backend SQL access layer."""

    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("BATMAN_DATABASE_URL") or DEFAULT_URL
        self.is_postgres = _is_postgres(self.url)
        self._lock = threading.RLock()
        self._conn = self._connect()

    # --- connection ---
    def _connect(self):
        if self.is_postgres:
            try:
                import psycopg  # type: ignore
                from psycopg.rows import dict_row  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dep
                raise RuntimeError(
                    "PostgreSQL URL configured but 'psycopg' is not installed. "
                    "Install with: pip install 'batman[postgres]' or pip install psycopg[binary]"
                ) from exc
            conn = psycopg.connect(self.url, autocommit=True, row_factory=dict_row)
            return conn
        # SQLite: accept sqlite:///path or a bare path.
        path = self.url
        if path.startswith("sqlite:///"):
            path = path[len("sqlite:///") :]
        elif path.startswith("sqlite://"):
            path = path[len("sqlite://") :]
        conn = sqlite3.connect(path or "batman.db", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    # --- placeholder translation ---
    def _translate(self, sql: str) -> str:
        # Callers use '?'. Postgres uses '%s'.
        return sql.replace("?", "%s") if self.is_postgres else sql

    def _rows_to_dicts(self, rows: Iterable) -> list[dict[str, Any]]:
        if self.is_postgres:
            return [dict(r) for r in rows]  # already dict_row
        return [dict(r) for r in rows]  # sqlite3.Row -> dict

    # --- operations ---
    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run an INSERT/UPDATE/DELETE/DDL. Returns affected row count."""
        sql = self._translate(sql)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rowcount = cur.rowcount
            if not self.is_postgres:
                self._conn.commit()
            cur.close()
            return rowcount

    def executescript(self, script: str) -> None:
        with self._lock:
            if self.is_postgres:
                cur = self._conn.cursor()
                cur.execute(script)
                cur.close()
            else:
                self._conn.executescript(script)
                self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        sql = self._translate(sql)
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        return self._rows_to_dicts(rows)

    def query_one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_INSTANCE: Database | None = None
_INSTANCE_LOCK = threading.Lock()


def get_database(url: str | None = None) -> Database:
    """Return a process-wide Database. If url is provided, a fresh instance is
    created (useful for tests / per-request DBs)."""
    global _INSTANCE
    if url is not None:
        return Database(url)
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = Database()
        return _INSTANCE


def reset_database_singleton() -> None:
    """Testing helper: drop the cached singleton."""
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is not None:
            try:
                _INSTANCE.close()
            except Exception:
                pass
        _INSTANCE = None
