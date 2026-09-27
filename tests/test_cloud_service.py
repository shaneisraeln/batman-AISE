"""Tests for the Phase 2 control-plane service (auth, tenancy, keys, upstream)."""

import os
import tempfile

import pytest

from batman.cloud import crypto
from batman.cloud.service import ControlPlaneService, ServiceError
from batman.db.database import Database


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    # Provide a Fernet key so upstream-secret encryption works in tests.
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_SECRET_KEY", "test-secret-key")
    # Service-layer tests use mock upstream hosts; allow past the SSRF guard.
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")


@pytest.fixture
def svc():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = ControlPlaneService(Database(f"sqlite:///{path}"))
    yield s
    s.db.close()
    try:
        os.remove(path)
    except OSError:
        pass


# ---- password + token ----
def test_password_hash_roundtrip():
    h = crypto.hash_password("supersecret")
    assert h != "supersecret" and "supersecret" not in h
    assert crypto.verify_password("supersecret", h)
    assert not crypto.verify_password("wrong", h)


def test_short_password_rejected():
    with pytest.raises(ValueError):
        crypto.hash_password("short")


def test_token_roundtrip_and_tamper():
    t = crypto.issue_token("user_1")
    assert crypto.verify_token(t) == "user_1"
    assert crypto.verify_token(t + "x") is None
    assert crypto.verify_token("garbage") is None


# ---- signup / login ----
def test_signup_and_login(svc):
    user = svc.signup("Alice@Example.com", "password123", "Alice")
    assert user.email == "alice@example.com"
    token = svc.login("alice@example.com", "password123")
    assert svc.user_from_token(token).user_id == user.user_id


def test_duplicate_email_rejected(svc):
    svc.signup("a@b.com", "password123")
    with pytest.raises(ServiceError):
        svc.signup("a@b.com", "password123")


def test_login_wrong_password(svc):
    svc.signup("a@b.com", "password123")
    with pytest.raises(ServiceError):
        svc.login("a@b.com", "nope")


# ---- projects / models / tenancy ----
def test_project_model_key_flow(svc):
    u = svc.signup("a@b.com", "password123")
    p = svc.create_project(u.user_id, "Fraud", "production")
    m = svc.register_model(u.user_id, p.project_id, "v1")
    raw, meta = svc.create_api_key(u.user_id, p.project_id, m.model_id, name="prod")
    assert raw.startswith("bm_live_")
    assert meta["model_id"] == m.model_id
    keys = svc.list_api_keys(u.user_id)
    assert len(keys) == 1 and "key_hash" not in keys[0]


def test_cannot_use_another_users_project(svc):
    u1 = svc.signup("u1@b.com", "password123")
    u2 = svc.signup("u2@b.com", "password123")
    p1 = svc.create_project(u1.user_id, "P1")
    # u2 cannot register a model under u1's project
    with pytest.raises(ServiceError):
        svc.register_model(u2.user_id, p1.project_id, "x")
    # u2 cannot mint a key on u1's project
    with pytest.raises(ServiceError):
        svc.create_api_key(u2.user_id, p1.project_id, "model_x")


def test_key_revocation_is_tenant_scoped(svc):
    u1 = svc.signup("u1@b.com", "password123")
    u2 = svc.signup("u2@b.com", "password123")
    p = svc.create_project(u1.user_id, "P")
    m = svc.register_model(u1.user_id, p.project_id, "v1")
    _, meta = svc.create_api_key(u1.user_id, p.project_id, m.model_id)
    assert svc.revoke_api_key(u2.user_id, meta["key_id"]) is False
    assert svc.revoke_api_key(u1.user_id, meta["key_id"]) is True


# ---- upstream config ----
def test_upstream_secret_is_encrypted_at_rest(svc):
    u = svc.signup("a@b.com", "password123")
    p = svc.create_project(u.user_id, "P")
    m = svc.register_model(u.user_id, p.project_id, "v1")
    svc.set_upstream(
        u.user_id, m.model_id, url="https://svc.example/predict",
        auth_type="bearer", auth_secret="super-upstream-token",
    )
    cfg = svc.get_upstream(m.model_id)
    # Stored value must be ciphertext, not the plaintext secret.
    assert cfg.auth_secret_enc is not None
    assert "super-upstream-token" not in cfg.auth_secret_enc
    assert crypto.decrypt_secret(cfg.auth_secret_enc) == "super-upstream-token"


def test_upstream_requires_owned_model(svc):
    u = svc.signup("a@b.com", "password123")
    with pytest.raises(ServiceError):
        svc.set_upstream(u.user_id, "model_not_mine", url="https://x/predict")
