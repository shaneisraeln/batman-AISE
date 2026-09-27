"""PostgreSQL parity tests.

These run ONLY when BATMAN_TEST_DATABASE_URL points at a reachable PostgreSQL
instance; otherwise they skip cleanly so the normal SQLite suite is unaffected.

To run (verified against PostgreSQL 16):
    docker run -d --name batman-pgtest \
        -e POSTGRES_USER=batman -e POSTGRES_PASSWORD=batmanpw -e POSTGRES_DB=batman_test \
        -p 5434:5432 postgres:16-alpine
    set BATMAN_TEST_DATABASE_URL=postgresql://batman:batmanpw@127.0.0.1:5434/batman_test
    python -m pytest tests/test_postgres.py -q
    docker rm -f batman-pgtest

Note: pick a host port that nothing else is bound to. A stale docker-proxy
binding on a reused port can silently forward to the wrong backend and produce
"password authentication failed" errors that look like a credential bug.

They verify the Postgres backend behaves like SQLite for the control plane:
schema init, auth, projects/models/keys, tenant isolation, telemetry, feedback.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

PG_URL = os.getenv("BATMAN_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL or not PG_URL.startswith(("postgres://", "postgresql://")),
    reason="BATMAN_TEST_DATABASE_URL not set to a PostgreSQL URL; skipping PG parity tests",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "pg-test-secret")
    from batman.cloud import crypto

    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())


@pytest.fixture
def db():
    """A Postgres-backed Database with schema initialized and tables cleared.

    Tables are truncated before each test so runs are isolated without dropping
    the schema.
    """
    from batman.db.database import Database
    from batman.db.schema import init_schema

    database = Database(PG_URL)
    init_schema(database)
    # Clean slate (order respects no hard FKs, but truncate all anyway).
    for t in ("feedback", "telemetry", "api_keys", "upstream_configs", "models", "projects", "users"):
        try:
            database.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    yield database
    database.close()


@pytest.fixture
def svc(db):
    from batman.cloud.service import ControlPlaneService

    return ControlPlaneService(db)


def _email():
    return f"pg-{uuid.uuid4().hex[:8]}@example.com"


# ---- schema ----
def test_pg_schema_has_all_tables(db):
    rows = db.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    names = {r["table_name"] for r in rows}
    for t in ("users", "projects", "models", "upstream_configs", "api_keys", "telemetry", "feedback"):
        assert t in names, f"missing table {t}"


# ---- auth ----
def test_pg_signup_login(svc):
    email = _email()
    user = svc.signup(email, "password123", "PG User")
    assert user.email == email
    token = svc.login(email, "password123")
    assert svc.user_from_token(token).user_id == user.user_id


def test_pg_duplicate_email_rejected(svc):
    from batman.cloud.service import ServiceError

    email = _email()
    svc.signup(email, "password123")
    with pytest.raises(ServiceError):
        svc.signup(email, "password123")


# ---- projects / models / keys ----
def test_pg_project_model_key_flow(svc):
    u = svc.signup(_email(), "password123")
    p = svc.create_project(u.user_id, "Fraud", "production")
    m = svc.register_model(u.user_id, p.project_id, "v1")
    raw, meta = svc.create_api_key(u.user_id, p.project_id, m.model_id, name="prod")
    assert raw.startswith("bm_live_")
    keys = svc.list_api_keys(u.user_id)
    assert len(keys) == 1 and "key_hash" not in keys[0]
    # revoke
    assert svc.revoke_api_key(u.user_id, meta["key_id"]) is True


# ---- tenant isolation ----
def test_pg_tenant_isolation(svc):
    from batman.cloud.service import ServiceError

    u1 = svc.signup(_email(), "password123")
    u2 = svc.signup(_email(), "password123")
    p1 = svc.create_project(u1.user_id, "Owned")
    # u2 cannot register a model under u1's project
    with pytest.raises(ServiceError):
        svc.register_model(u2.user_id, p1.project_id, "x")
    # u2 sees none of u1's projects
    assert svc.list_projects(u2.user_id) == []


# ---- telemetry + feedback ----
def test_pg_telemetry_and_feedback(svc, db):
    from batman.telemetry.schema import TelemetryEvent, new_request_id, utcnow_iso

    u = svc.signup(_email(), "password123")
    p = svc.create_project(u.user_id, "P")
    m = svc.register_model(u.user_id, p.project_id, "v1")
    rid = new_request_id()
    svc.telemetry.record(
        TelemetryEvent(
            request_id=rid, timestamp=utcnow_iso(), project_id=p.project_id,
            model_id=m.model_id, session_id="s", detector_version="1.0",
            features={"request_rate": 10.0}, anomaly_score=0.9, extraction_score=0.8,
            threat_type="MODEL_EXTRACTION", threat_level="HIGH", action="BLOCK",
            latency_ms=12.0, reason="test",
        )
    )
    # tenant-scoped metrics + threats reflect the row
    metrics = svc.telemetry.metrics_summary(project_ids=[p.project_id])
    assert metrics["total_requests"] == 1 and metrics["blocked"] == 1
    threats = svc.telemetry.get_threats(project_ids=[p.project_id])
    assert any(t["request_id"] == rid for t in threats)
    # feedback (tenant-scoped)
    svc.submit_feedback(u.user_id, rid, "TRUE_POSITIVE", "pg note")
    fb = svc.list_feedback(u.user_id)
    assert any(f["request_id"] == rid and f["label"] == "TRUE_POSITIVE" for f in fb)


def test_pg_upstream_encrypted(svc):
    from batman.cloud import crypto

    u = svc.signup(_email(), "password123")
    p = svc.create_project(u.user_id, "P")
    m = svc.register_model(u.user_id, p.project_id, "v1")
    svc.set_upstream(u.user_id, m.model_id, url="https://svc/predict",
                     auth_type="bearer", auth_secret="pg-secret")
    cfg = svc.get_upstream(m.model_id)
    assert cfg.auth_secret_enc and "pg-secret" not in cfg.auth_secret_enc
    assert crypto.decrypt_secret(cfg.auth_secret_enc) == "pg-secret"
