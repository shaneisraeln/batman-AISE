"""SQLite/PostgreSQL-backed persistence for API keys, telemetry, and feedback.

Phase 2 note: this class now delegates to the backend-agnostic ``batman.db``
layer (SQLite dev default, PostgreSQL for production) while preserving its exact
Phase 1 public interface, so the engine, gateway, and existing tests keep
working without change. Feedback remains separate from immutable telemetry.

Construction:
  - TelemetryStore("batman.db")            -> SQLite file (Phase 1 style)
  - TelemetryStore(url="postgresql://...") -> PostgreSQL
  - BATMAN_DATABASE_URL env var overrides when no explicit path/url is given.
"""

from __future__ import annotations

from typing import Any

from batman.db.database import Database
from batman.db.repositories import (
    ApiKeyRepository,
    FeedbackRepository,
    TelemetryRepository,
)
from batman.db.schema import init_schema
from batman.gateway.auth import APIKeyRecord
from batman.telemetry.schema import FeedbackRecord, TelemetryEvent


class TelemetryStore:
    def __init__(self, db_path: str | None = None, url: str | None = None):
        if url is not None:
            resolved = url
        elif db_path is not None:
            # Preserve Phase 1 behavior: a bare path means a SQLite file.
            resolved = db_path if "://" in db_path else f"sqlite:///{db_path}"
        else:
            resolved = None  # let Database read BATMAN_DATABASE_URL / default
        self.db = Database(resolved) if resolved is not None else Database()
        self.db_path = db_path
        init_schema(self.db)
        self._keys = ApiKeyRepository(self.db)
        self._telemetry = TelemetryRepository(self.db)
        self._feedback = FeedbackRepository(self.db)

    # --- API keys (Phase 1 interface) ---
    def save_api_key(self, record: APIKeyRecord) -> None:
        self._keys.save(record)

    def get_api_key_by_hash(self, key_hash: str) -> APIKeyRecord | None:
        return self._keys.get_by_hash(key_hash)

    def get_api_key_by_id(self, key_id: str) -> APIKeyRecord | None:
        return self._keys.get_by_id(key_id)

    def revoke_api_key(self, key_id: str) -> bool:
        return self._keys.revoke(key_id)

    # --- Telemetry (Phase 1 interface) ---
    def record_telemetry(self, event: TelemetryEvent) -> None:
        self._telemetry.record(event)

    def get_threats(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._telemetry.get_threats(limit=limit)

    def get_telemetry(self, request_id: str) -> dict[str, Any] | None:
        return self._telemetry.get(request_id)

    def get_recent_telemetry(self, limit: int = 500) -> list[dict[str, Any]]:
        return self._telemetry.get_recent(limit=limit)

    def metrics_summary(self) -> dict[str, Any]:
        return self._telemetry.metrics_summary()

    # --- Feedback (Phase 1 interface) ---
    def record_feedback(self, record: FeedbackRecord) -> None:
        self._feedback.record(record)

    def get_feedback(self, request_id: str | None = None) -> list[dict[str, Any]]:
        return self._feedback.get(request_id)

    def close(self) -> None:
        self.db.close()
