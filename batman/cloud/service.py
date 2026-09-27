"""Control-plane service layer.

Wires the persistence repositories together with authentication and tenant-safe
operations. All resource operations require a ``user_id`` and verify ownership,
so a caller can never act on another tenant's projects, models, or keys.

The raw API key is returned only once, at creation, and is never stored or
logged. Upstream credentials are encrypted before storage.
"""

from __future__ import annotations

import secrets
from dataclasses import asdict
from datetime import datetime, timezone

from batman.cloud import crypto
from batman.cloud.ssrf import UpstreamURLError, validate_upstream_url
from batman.db.database import Database
from batman.db.models import Model, Project, UpstreamConfig, User
from batman.db.repositories import (
    ApiKeyRepository,
    FeedbackRepository,
    ModelRepository,
    ProjectRepository,
    TelemetryRepository,
    UpstreamConfigRepository,
    UserRepository,
)
from batman.db.schema import init_schema
from batman.gateway.auth import (
    APIKeyRecord,
    generate_api_key,
    hash_key,
)
from batman.telemetry.schema import VALID_FEEDBACK_LABELS, FeedbackRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


class ServiceError(Exception):
    """Business-rule violation (e.g. duplicate email, not found, not owned)."""


class ControlPlaneService:
    def __init__(self, db: Database):
        self.db = db
        init_schema(db)
        self.users = UserRepository(db)
        self.projects = ProjectRepository(db)
        self.models = ModelRepository(db)
        self.keys = ApiKeyRepository(db)
        self.upstreams = UpstreamConfigRepository(db)
        self.telemetry = TelemetryRepository(db)
        self.feedback = FeedbackRepository(db)

    # ---- auth ----
    def signup(self, email: str, password: str, display_name: str | None = None) -> User:
        email = (email or "").strip().lower()
        if "@" not in email:
            raise ServiceError("invalid_email")
        if self.users.get_by_email(email):
            raise ServiceError("email_already_registered")
        user = User(
            user_id=_uid("user"),
            email=email,
            password_hash=crypto.hash_password(password),
            display_name=display_name,
            status="active",
            created_at=_now(),
        )
        self.users.create(user)
        return user

    def login(self, email: str, password: str) -> str:
        email = (email or "").strip().lower()
        user = self.users.get_by_email(email)
        # Constant-ish behavior: always run a verify to reduce user enumeration.
        stored = user.password_hash if user else "pbkdf2_sha256$1$AA==$AA=="
        ok = crypto.verify_password(password, stored)
        if not user or not ok or user.status != "active":
            raise ServiceError("invalid_credentials")
        return crypto.issue_token(user.user_id)

    def user_from_token(self, token: str) -> User | None:
        uid = crypto.verify_token(token)
        if not uid:
            return None
        return self.users.get_by_id(uid)

    # ---- projects ----
    def create_project(self, user_id: str, name: str, environment: str = "development") -> Project:
        if environment not in ("development", "staging", "production"):
            raise ServiceError("invalid_environment")
        project = Project(_uid("proj"), user_id, name or "Untitled", environment, _now())
        self.projects.create(project)
        return project

    def list_projects(self, user_id: str) -> list[Project]:
        return self.projects.list_for_user(user_id)

    # ---- models ----
    def register_model(self, user_id: str, project_id: str, name: str) -> Model:
        if not self.projects.get_owned(project_id, user_id):
            raise ServiceError("project_not_found")
        model = Model(_uid("model"), project_id, user_id, name or "model", "active", _now())
        self.models.create(model)
        return model

    def list_models(self, user_id: str, project_id: str | None = None) -> list[Model]:
        if project_id:
            if not self.projects.get_owned(project_id, user_id):
                raise ServiceError("project_not_found")
            return self.models.list_for_project(project_id, user_id)
        return self.models.list_for_user(user_id)

    # ---- API keys ----
    def create_api_key(
        self, user_id: str, project_id: str, model_id: str, name: str | None = None,
        expires_at: str | None = None,
    ) -> tuple[str, dict]:
        """Create a key for an owned model. Returns (raw_key_once, metadata)."""
        if not self.projects.get_owned(project_id, user_id):
            raise ServiceError("project_not_found")
        if not self.models.get_owned(model_id, user_id):
            raise ServiceError("model_not_found")
        raw = generate_api_key()
        record = APIKeyRecord(
            key_id=_uid("key"),
            key_hash=hash_key(raw),
            project_id=project_id,
            model_id=model_id,
            status="active",
            created_at=_now(),
            expires_at=expires_at,
        )
        self.keys.save(record, user_id=user_id, name=name)
        meta = {
            "key_id": record.key_id, "project_id": project_id, "model_id": model_id,
            "name": name, "status": "active", "created_at": record.created_at,
            "expires_at": expires_at,
        }
        return raw, meta  # raw returned ONCE

    def list_api_keys(self, user_id: str) -> list[dict]:
        return self.keys.list_for_user(user_id)  # never includes hash/secret

    def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        return self.keys.revoke_owned(key_id, user_id)

    # ---- upstream config (existing-ML-API protection) ----
    def set_upstream(
        self, user_id: str, model_id: str, url: str, method: str = "POST",
        predict_path: str = "/predict", request_format: str = "instances",
        response_format: str = "predictions", auth_type: str = "none",
        auth_secret: str | None = None, auth_header_name: str | None = None,
        timeout_s: float = 15.0,
    ) -> UpstreamConfig:
        model = self.models.get_owned(model_id, user_id)
        if not model:
            raise ServiceError("model_not_found")
        # SSRF guard: reject upstream URLs pointing at loopback / private /
        # link-local (incl. cloud metadata) addresses before storing them.
        try:
            validate_upstream_url(url)
        except UpstreamURLError as e:
            raise ServiceError(str(e))
        enc = None
        if auth_secret:
            enc = crypto.encrypt_secret(auth_secret)  # fails closed if no key
        cfg = UpstreamConfig(
            model_id=model_id, user_id=user_id, project_id=model.project_id,
            url=url, method=method, predict_path=predict_path,
            request_format=request_format, response_format=response_format,
            auth_type=auth_type, auth_secret_enc=enc, auth_header_name=auth_header_name,
            timeout_s=timeout_s, created_at=_now(), updated_at=_now(),
        )
        self.upstreams.upsert(cfg)
        return cfg

    def get_upstream(self, model_id: str) -> UpstreamConfig | None:
        return self.upstreams.get_for_model(model_id)

    def project_ids_for_user(self, user_id: str) -> list[str]:
        return [p.project_id for p in self.projects.list_for_user(user_id)]

    # ---- analyst feedback (tenant-scoped) ----
    def submit_feedback(
        self, user_id: str, request_id: str, label: str, analyst_note: str = ""
    ) -> FeedbackRecord:
        """Record analyst feedback on a threat, only if the underlying telemetry
        row belongs to one of the user's projects (tenant isolation)."""
        if label not in VALID_FEEDBACK_LABELS:
            raise ServiceError("invalid_label")
        event = self.telemetry.get(request_id)
        owned = set(self.project_ids_for_user(user_id))
        if not event or event.get("project_id") not in owned:
            raise ServiceError("threat_not_found")
        record = FeedbackRecord(request_id=request_id, label=label, analyst_note=analyst_note)
        self.feedback.record(record)
        return record

    def list_feedback(self, user_id: str, limit: int = 200) -> list[dict]:
        return self.feedback.list_for_projects(self.project_ids_for_user(user_id), limit=limit)
