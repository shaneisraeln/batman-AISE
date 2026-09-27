"""Repositories — tenant-aware persistence over the Database abstraction.

Every read that returns tenant-owned data accepts a ``user_id`` (or is reached
only after an ownership check), so cross-tenant access is structurally hard.
Telemetry/feedback repositories preserve the exact Phase 1 semantics.
"""

from __future__ import annotations

import json
from typing import Any

from batman.db.database import Database
from batman.db.models import Model, Project, UpstreamConfig, User
from batman.gateway.auth import APIKeyRecord


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, user: User) -> None:
        self.db.execute(
            """INSERT INTO users (user_id, email, password_hash, display_name, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user.user_id, user.email, user.password_hash, user.display_name, user.status, user.created_at),
        )

    def get_by_email(self, email: str) -> User | None:
        row = self.db.query_one("SELECT * FROM users WHERE email = ?", (email,))
        return self._row(row) if row else None

    def get_by_id(self, user_id: str) -> User | None:
        row = self.db.query_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self._row(row) if row else None

    @staticmethod
    def _row(r: dict) -> User:
        return User(
            user_id=r["user_id"], email=r["email"], password_hash=r["password_hash"],
            display_name=r.get("display_name"), status=r["status"], created_at=r["created_at"],
        )


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------
class ProjectRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, project: Project) -> None:
        self.db.execute(
            """INSERT INTO projects (project_id, user_id, name, environment, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (project.project_id, project.user_id, project.name, project.environment, project.created_at),
        )

    def list_for_user(self, user_id: str) -> list[Project]:
        rows = self.db.query(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        )
        return [self._row(r) for r in rows]

    def get_owned(self, project_id: str, user_id: str) -> Project | None:
        """Fetch a project only if it belongs to the user (tenant isolation)."""
        row = self.db.query_one(
            "SELECT * FROM projects WHERE project_id = ? AND user_id = ?", (project_id, user_id)
        )
        return self._row(row) if row else None

    @staticmethod
    def _row(r: dict) -> Project:
        return Project(
            project_id=r["project_id"], user_id=r["user_id"], name=r["name"],
            environment=r["environment"], created_at=r["created_at"],
        )


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------
class ModelRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, model: Model) -> None:
        self.db.execute(
            """INSERT INTO models (model_id, project_id, user_id, name, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (model.model_id, model.project_id, model.user_id, model.name, model.status, model.created_at),
        )

    def list_for_project(self, project_id: str, user_id: str) -> list[Model]:
        rows = self.db.query(
            "SELECT * FROM models WHERE project_id = ? AND user_id = ? ORDER BY created_at DESC",
            (project_id, user_id),
        )
        return [self._row(r) for r in rows]

    def list_for_user(self, user_id: str) -> list[Model]:
        rows = self.db.query(
            "SELECT * FROM models WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        )
        return [self._row(r) for r in rows]

    def get_owned(self, model_id: str, user_id: str) -> Model | None:
        row = self.db.query_one(
            "SELECT * FROM models WHERE model_id = ? AND user_id = ?", (model_id, user_id)
        )
        return self._row(row) if row else None

    @staticmethod
    def _row(r: dict) -> Model:
        return Model(
            model_id=r["model_id"], project_id=r["project_id"], user_id=r["user_id"],
            name=r["name"], status=r["status"], created_at=r["created_at"],
        )


# --------------------------------------------------------------------------
# Upstream configs (existing-ML-API protection)
# --------------------------------------------------------------------------
class UpstreamConfigRepository:
    def __init__(self, db: Database):
        self.db = db

    def upsert(self, cfg: UpstreamConfig) -> None:
        existing = self.db.query_one(
            "SELECT model_id FROM upstream_configs WHERE model_id = ?", (cfg.model_id,)
        )
        if existing:
            self.db.execute(
                """UPDATE upstream_configs SET url=?, method=?, predict_path=?,
                   request_format=?, response_format=?, auth_type=?, auth_secret_enc=?,
                   auth_header_name=?, timeout_s=?, updated_at=? WHERE model_id=?""",
                (cfg.url, cfg.method, cfg.predict_path, cfg.request_format, cfg.response_format,
                 cfg.auth_type, cfg.auth_secret_enc, cfg.auth_header_name, cfg.timeout_s,
                 cfg.updated_at, cfg.model_id),
            )
        else:
            self.db.execute(
                """INSERT INTO upstream_configs (model_id, user_id, project_id, url, method,
                   predict_path, request_format, response_format, auth_type, auth_secret_enc,
                   auth_header_name, timeout_s, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (cfg.model_id, cfg.user_id, cfg.project_id, cfg.url, cfg.method, cfg.predict_path,
                 cfg.request_format, cfg.response_format, cfg.auth_type, cfg.auth_secret_enc,
                 cfg.auth_header_name, cfg.timeout_s, cfg.created_at, cfg.updated_at),
            )

    def get_for_model(self, model_id: str) -> UpstreamConfig | None:
        row = self.db.query_one(
            "SELECT * FROM upstream_configs WHERE model_id = ?", (model_id,)
        )
        return self._row(row) if row else None

    @staticmethod
    def _row(r: dict) -> UpstreamConfig:
        return UpstreamConfig(
            model_id=r["model_id"], user_id=r["user_id"], project_id=r["project_id"],
            url=r["url"], method=r["method"], predict_path=r["predict_path"],
            request_format=r["request_format"], response_format=r["response_format"],
            auth_type=r["auth_type"], auth_secret_enc=r.get("auth_secret_enc"),
            auth_header_name=r.get("auth_header_name"),
            timeout_s=float(r["timeout_s"]), created_at=r["created_at"], updated_at=r.get("updated_at"),
        )


# --------------------------------------------------------------------------
# API keys (extends Phase 1 with user_id, name, last_used_at)
# --------------------------------------------------------------------------
class ApiKeyRepository:
    def __init__(self, db: Database):
        self.db = db

    def save(self, record: APIKeyRecord, user_id: str | None = None, name: str | None = None) -> None:
        self.db.execute(
            """INSERT INTO api_keys
               (key_id, key_hash, project_id, model_id, user_id, name, status, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.key_id, record.key_hash, record.project_id, record.model_id,
             user_id, name, record.status, record.created_at, record.expires_at),
        )

    def get_by_hash(self, key_hash: str) -> APIKeyRecord | None:
        row = self.db.query_one("SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,))
        return self._row(row) if row else None

    def get_by_id(self, key_id: str) -> APIKeyRecord | None:
        row = self.db.query_one("SELECT * FROM api_keys WHERE key_id = ?", (key_id,))
        return self._row(row) if row else None

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            """SELECT key_id, project_id, model_id, name, status, created_at, expires_at, last_used_at
               FROM api_keys WHERE user_id = ? ORDER BY created_at DESC""",
            (user_id,),
        )
        return rows  # never includes key_hash or raw secret

    def revoke_owned(self, key_id: str, user_id: str) -> bool:
        n = self.db.execute(
            "UPDATE api_keys SET status = 'revoked' WHERE key_id = ? AND user_id = ?",
            (key_id, user_id),
        )
        return n > 0

    def revoke(self, key_id: str) -> bool:
        return self.db.execute(
            "UPDATE api_keys SET status = 'revoked' WHERE key_id = ?", (key_id,)
        ) > 0

    def touch_last_used(self, key_id: str, when_iso: str) -> None:
        self.db.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (when_iso, key_id)
        )

    @staticmethod
    def _row(r: dict) -> APIKeyRecord:
        return APIKeyRecord(
            key_id=r["key_id"], key_hash=r["key_hash"], project_id=r["project_id"],
            model_id=r["model_id"], status=r["status"], created_at=r["created_at"],
            expires_at=r.get("expires_at"),
        )


# --------------------------------------------------------------------------
# Telemetry (preserves Phase 1 semantics) + tenant-scoped queries
# --------------------------------------------------------------------------
class TelemetryRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, event) -> None:
        self.db.execute(
            """INSERT OR REPLACE INTO telemetry
               (request_id, timestamp, project_id, model_id, session_id, detector_version,
                features, anomaly_score, extraction_score, threat_type, threat_level,
                action, latency_ms, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            if not self.db.is_postgres else
            """INSERT INTO telemetry
               (request_id, timestamp, project_id, model_id, session_id, detector_version,
                features, anomaly_score, extraction_score, threat_type, threat_level,
                action, latency_ms, reason)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (request_id) DO UPDATE SET
                 timestamp=EXCLUDED.timestamp, action=EXCLUDED.action,
                 threat_type=EXCLUDED.threat_type, threat_level=EXCLUDED.threat_level""",
            (event.request_id, event.timestamp, event.project_id, event.model_id,
             event.session_id, event.detector_version, json.dumps(event.features, default=str),
             event.anomaly_score, event.extraction_score, event.threat_type, event.threat_level,
             event.action, event.latency_ms, event.reason),
        )

    def get(self, request_id: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM telemetry WHERE request_id = ?", (request_id,))
        return self._parse(row) if row else None

    def get_threats(self, limit: int = 100, project_ids: list[str] | None = None) -> list[dict]:
        if project_ids is not None:
            if not project_ids:
                return []
            placeholders = ",".join("?" for _ in project_ids)
            rows = self.db.query(
                f"""SELECT * FROM telemetry WHERE threat_type != 'NONE'
                    AND project_id IN ({placeholders})
                    ORDER BY timestamp DESC LIMIT ?""",
                (*project_ids, limit),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM telemetry WHERE threat_type != 'NONE' ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [self._parse(r) for r in rows]

    def get_recent(self, limit: int = 500) -> list[dict]:
        rows = self.db.query(
            "SELECT * FROM telemetry ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        return [self._parse(r) for r in rows]

    def metrics_summary(self, project_ids: list[str] | None = None) -> dict:
        where, params = "", ()
        if project_ids is not None:
            if not project_ids:
                return _empty_metrics()
            placeholders = ",".join("?" for _ in project_ids)
            where = f" WHERE project_id IN ({placeholders})"
            params = tuple(project_ids)
        total = (self.db.query_one(f"SELECT COUNT(*) c FROM telemetry{where}", params) or {}).get("c", 0)
        by_action = self.db.query(f"SELECT action, COUNT(*) c FROM telemetry{where} GROUP BY action", params)
        by_threat = self.db.query(f"SELECT threat_type, COUNT(*) c FROM telemetry{where} GROUP BY threat_type", params)
        avg_latency = (self.db.query_one(f"SELECT AVG(latency_ms) a FROM telemetry{where}", params) or {}).get("a")
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
    def _parse(r: dict) -> dict:
        d = dict(r)
        try:
            d["features"] = json.loads(d.get("features") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["features"] = {}
        return d


class FeedbackRepository:
    def __init__(self, db: Database):
        self.db = db

    def record(self, record) -> None:
        self.db.execute(
            "INSERT INTO feedback (request_id, label, analyst_note, created_at) VALUES (?, ?, ?, ?)",
            (record.request_id, record.label, record.analyst_note, record.created_at),
        )

    def get(self, request_id: str | None = None) -> list[dict]:
        if request_id:
            return self.db.query(
                "SELECT * FROM feedback WHERE request_id = ? ORDER BY created_at DESC", (request_id,)
            )
        return self.db.query("SELECT * FROM feedback ORDER BY created_at DESC LIMIT 500")

    def list_for_projects(self, project_ids: list[str], limit: int = 200) -> list[dict]:
        """Tenant-scoped feedback: only rows whose telemetry belongs to one of
        the caller's projects. Joins feedback -> telemetry on request_id."""
        if not project_ids:
            return []
        placeholders = ",".join("?" for _ in project_ids)
        return self.db.query(
            f"""SELECT f.request_id, f.label, f.analyst_note, f.created_at,
                       t.project_id, t.model_id, t.threat_type, t.threat_level
                FROM feedback f
                JOIN telemetry t ON t.request_id = f.request_id
                WHERE t.project_id IN ({placeholders})
                ORDER BY f.created_at DESC LIMIT ?""",
            (*project_ids, limit),
        )


def _empty_metrics() -> dict:
    return {
        "total_requests": 0, "allowed": 0, "blocked": 0, "rate_limited": 0,
        "escalated": 0, "actions": {}, "threat_categories": {}, "active_threats": 0,
        "avg_latency_ms": 0.0,
    }
