"""SQLite-backed persistence for API keys, telemetry, and feedback.

Feedback is stored in a separate table from immutable telemetry.
Thread-safe via a lock; connections use check_same_thread=False for FastAPI.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from batman.gateway.auth import APIKeyRecord
from batman.telemetry.schema import FeedbackRecord, TelemetryEvent


class TelemetryStore:
    def __init__(self, db_path: str = "batman.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_id TEXT PRIMARY KEY,
                    key_hash TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                );

                CREATE TABLE IF NOT EXISTS telemetry (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    project_id TEXT,
                    model_id TEXT,
                    session_id TEXT,
                    detector_version TEXT,
                    features TEXT,
                    anomaly_score REAL,
                    extraction_score REAL,
                    threat_type TEXT,
                    threat_level TEXT,
                    action TEXT,
                    latency_ms REAL,
                    reason TEXT
                );

                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    analyst_note TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(timestamp);
                CREATE INDEX IF NOT EXISTS idx_telemetry_threat ON telemetry(threat_type);
                CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session_id);
                """
            )
            self._conn.commit()

    # --- API keys ---
    def save_api_key(self, record: APIKeyRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO api_keys
                   (key_id, key_hash, project_id, model_id, status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.key_id,
                    record.key_hash,
                    record.project_id,
                    record.model_id,
                    record.status,
                    record.created_at,
                    record.expires_at,
                ),
            )
            self._conn.commit()

    def get_api_key_by_hash(self, key_hash: str) -> APIKeyRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()
        return self._row_to_key(row) if row else None

    def get_api_key_by_id(self, key_id: str) -> APIKeyRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM api_keys WHERE key_id = ?", (key_id,)
            ).fetchone()
        return self._row_to_key(row) if row else None

    def revoke_api_key(self, key_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET status = 'revoked' WHERE key_id = ?", (key_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _row_to_key(row: sqlite3.Row) -> APIKeyRecord:
        return APIKeyRecord(
            key_id=row["key_id"],
            key_hash=row["key_hash"],
            project_id=row["project_id"],
            model_id=row["model_id"],
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    # --- Telemetry ---
    def record_telemetry(self, event: TelemetryEvent) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO telemetry
                   (request_id, timestamp, project_id, model_id, session_id,
                    detector_version, features, anomaly_score, extraction_score,
                    threat_type, threat_level, action, latency_ms, reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.request_id,
                    event.timestamp,
                    event.project_id,
                    event.model_id,
                    event.session_id,
                    event.detector_version,
                    json.dumps(event.features, default=str),
                    event.anomaly_score,
                    event.extraction_score,
                    event.threat_type,
                    event.threat_level,
                    event.action,
                    event.latency_ms,
                    event.reason,
                ),
            )
            self._conn.commit()

    def get_threats(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM telemetry
                   WHERE threat_type != 'NONE'
                   ORDER BY timestamp DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [self._row_to_event_dict(r) for r in rows]

    def get_telemetry(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM telemetry WHERE request_id = ?", (request_id,)
            ).fetchone()
        return self._row_to_event_dict(row) if row else None

    def get_recent_telemetry(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM telemetry ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_event_dict(r) for r in rows]

    def metrics_summary(self) -> dict[str, Any]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) c FROM telemetry").fetchone()["c"]
            by_action = self._conn.execute(
                "SELECT action, COUNT(*) c FROM telemetry GROUP BY action"
            ).fetchall()
            by_threat = self._conn.execute(
                "SELECT threat_type, COUNT(*) c FROM telemetry GROUP BY threat_type"
            ).fetchall()
            avg_latency = self._conn.execute(
                "SELECT AVG(latency_ms) a FROM telemetry"
            ).fetchone()["a"]
        actions = {r["action"]: r["c"] for r in by_action}
        threats = {r["threat_type"]: r["c"] for r in by_threat}
        return {
            "total_requests": total,
            "allowed": actions.get("ALLOW", 0) + actions.get("LOG", 0),
            "blocked": actions.get("BLOCK", 0),
            "rate_limited": actions.get("RATE_LIMIT", 0),
            "escalated": actions.get("ESCALATE", 0),
            "actions": actions,
            "threat_categories": {k: v for k, v in threats.items() if k != "NONE"},
            "active_threats": sum(v for k, v in threats.items() if k != "NONE"),
            "avg_latency_ms": round(avg_latency, 3) if avg_latency else 0.0,
        }

    @staticmethod
    def _row_to_event_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        try:
            d["features"] = json.loads(d.get("features") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["features"] = {}
        return d

    # --- Feedback (separate from immutable telemetry) ---
    def record_feedback(self, record: FeedbackRecord) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO feedback (request_id, label, analyst_note, created_at)
                   VALUES (?, ?, ?, ?)""",
                (record.request_id, record.label, record.analyst_note, record.created_at),
            )
            self._conn.commit()

    def get_feedback(self, request_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if request_id:
                rows = self._conn.execute(
                    "SELECT * FROM feedback WHERE request_id = ? ORDER BY created_at DESC",
                    (request_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM feedback ORDER BY created_at DESC LIMIT 500"
                ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
