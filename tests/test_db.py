"""Tests for the Phase 2 persistence layer (batman.db)."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from batman.db.database import Database
from batman.db.models import Model, Project, UpstreamConfig, User
from batman.db.repositories import (
    ApiKeyRepository,
    ModelRepository,
    ProjectRepository,
    UpstreamConfigRepository,
    UserRepository,
)
from batman.db.schema import init_schema
from batman.gateway.auth import APIKeyRecord, generate_api_key, hash_key
from batman.telemetry.store import TelemetryStore


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    database = Database(f"sqlite:///{path}")
    init_schema(database)
    yield database
    database.close()
    try:
        os.remove(path)
    except OSError:
        pass


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_schema_creates_all_tables(db):
    tables = {r["name"] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in ("users", "projects", "models", "upstream_configs", "api_keys", "telemetry", "feedback"):
        assert t in tables


def test_user_project_model_hierarchy(db):
    users = UserRepository(db)
    projects = ProjectRepository(db)
    models = ModelRepository(db)

    users.create(User("u1", "a@b.com", "hash", "Alice", "active", _now()))
    assert users.get_by_email("a@b.com").user_id == "u1"

    projects.create(Project("p1", "u1", "Fraud", "production", _now()))
    models.create(Model("m1", "p1", "u1", "v1", "active", _now()))

    assert len(projects.list_for_user("u1")) == 1
    assert len(models.list_for_project("p1", "u1")) == 1


def test_tenant_isolation_projects(db):
    projects = ProjectRepository(db)
    projects.create(Project("p1", "u1", "Owned", "development", _now()))
    # Another user must not be able to fetch it.
    assert projects.get_owned("p1", "u1") is not None
    assert projects.get_owned("p1", "u2") is None


def test_tenant_isolation_models(db):
    models = ModelRepository(db)
    models.create(Model("m1", "p1", "u1", "v1", "active", _now()))
    assert models.get_owned("m1", "u1") is not None
    assert models.get_owned("m1", "u2") is None


def test_api_key_repo_never_returns_hash_in_listing(db):
    keys = ApiKeyRepository(db)
    raw = generate_api_key()
    rec = APIKeyRecord("key_1", hash_key(raw), "p1", "m1", "active", _now(), None)
    keys.save(rec, user_id="u1", name="prod key")
    listing = keys.list_for_user("u1")
    assert len(listing) == 1
    assert "key_hash" not in listing[0]
    assert listing[0]["name"] == "prod key"


def test_api_key_revoke_is_tenant_scoped(db):
    keys = ApiKeyRepository(db)
    raw = generate_api_key()
    keys.save(APIKeyRecord("key_1", hash_key(raw), "p1", "m1", "active", _now(), None), user_id="u1")
    # wrong tenant cannot revoke
    assert keys.revoke_owned("key_1", "u2") is False
    assert keys.get_by_id("key_1").status == "active"
    # owner can
    assert keys.revoke_owned("key_1", "u1") is True
    assert keys.get_by_id("key_1").status == "revoked"


def test_upstream_config_upsert(db):
    repo = UpstreamConfigRepository(db)
    cfg = UpstreamConfig("m1", "u1", "p1", "https://svc/predict", created_at=_now())
    repo.upsert(cfg)
    got = repo.get_for_model("m1")
    assert got.url == "https://svc/predict"
    # update
    cfg.url = "https://svc2/predict"
    cfg.updated_at = _now()
    repo.upsert(cfg)
    assert repo.get_for_model("m1").url == "https://svc2/predict"


def test_telemetrystore_still_works_via_new_layer():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = TelemetryStore(path)  # bare path -> sqlite (Phase 1 style)
    raw = generate_api_key()
    store.save_api_key(APIKeyRecord("k", hash_key(raw), "p", "m", "active", _now(), None))
    assert store.get_api_key_by_hash(hash_key(raw)).project_id == "p"
    store.close()
    os.remove(path)


def test_migration_adds_columns_to_legacy_table():
    """A pre-Phase-2 api_keys table (no user_id/name/last_used_at) gets upgraded."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    legacy = Database(f"sqlite:///{path}")
    legacy.executescript(
        """CREATE TABLE api_keys (key_id TEXT PRIMARY KEY, key_hash TEXT UNIQUE,
           project_id TEXT, model_id TEXT, status TEXT, created_at TEXT, expires_at TEXT);"""
    )
    init_schema(legacy)  # should ALTER TABLE to add the new columns
    cols = {r["name"] for r in legacy.query("PRAGMA table_info(api_keys)")}
    assert {"user_id", "name", "last_used_at"}.issubset(cols)
    legacy.close()
    os.remove(path)
