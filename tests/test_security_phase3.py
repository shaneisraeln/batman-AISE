"""Phase 3 security audit — automated adversarial tests.

These tests encode the Phase 3 security review as executable checks so the
findings stay true as the code evolves. They cover:

  - authentication: hashing, token expiry/tamper, protected-route gating,
    no-secret-leak in error bodies, user-enumeration resistance
  - API-key lifecycle: create -> display-once -> use -> revoke -> reuse-denied,
    expiry enforcement, hash-only storage, keys never returned in list/telemetry
  - tenant isolation across projects/models/keys/telemetry/threats/feedback/
    upstream (see also test_security_isolation.py)
  - SSRF mitigation on upstream URLs (see test_security_ssrf.py)

They use the real cloud app via TestClient with a stubbed upstream model.
"""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "phase3-test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from batman.cloud.app import create_cloud_app

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    app = create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False)
    yield TestClient(app)
    try:
        os.remove(path)
    except OSError:
        pass


def _auth(client, email="sec@b.com", password="password123"):
    client.post("/auth/signup", json={"email": email, "password": password})
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _onboard(client, email="sec@b.com"):
    h = _auth(client, email)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(f"/models/{m['model_id']}/upstream", json={"url": "http://upstream.test/predict"}, headers=h)
    created = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()
    return h, p, m, created


# ---------------------------------------------------------------- authentication
def test_password_is_hashed_not_stored_plaintext():
    h = crypto.hash_password("supersecret123")
    assert "supersecret123" not in h
    assert h.startswith("pbkdf2_sha256$")
    assert crypto.verify_password("supersecret123", h) is True
    assert crypto.verify_password("wrong", h) is False


def test_short_password_rejected(client):
    r = client.post("/auth/signup", json={"email": "x@y.com", "password": "short"})
    assert r.status_code == 422  # pydantic min_length


def test_protected_routes_require_bearer(client):
    for path in ("/projects", "/models", "/keys", "/v1/metrics", "/v1/threats", "/v1/feedback", "/auth/me"):
        assert client.get(path).status_code == 401, path


def test_tampered_token_rejected(client):
    h = _auth(client)
    tok = h["Authorization"].split(" ", 1)[1]
    body, sig = tok.split(".")
    forged = {"Authorization": f"Bearer {body}.{'A' * len(sig)}"}
    assert client.get("/auth/me", headers=forged).status_code == 401


def test_expired_token_rejected(client, monkeypatch):
    # Issue a token that is already expired.
    client.post("/auth/signup", json={"email": "exp@b.com", "password": "password123"})
    uid = client.post("/auth/login", json={"email": "exp@b.com", "password": "password123"})
    # Forge an expired token for the same signing secret.
    expired = crypto.issue_token("user_whatever", ttl_seconds=-10)
    assert crypto.verify_token(expired) is None
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_invalid_credentials_do_not_reveal_user_existence(client):
    client.post("/auth/signup", json={"email": "real@b.com", "password": "password123"})
    # Wrong password for a real user vs a nonexistent user: identical response.
    r1 = client.post("/auth/login", json={"email": "real@b.com", "password": "wrongpass1"})
    r2 = client.post("/auth/login", json={"email": "ghost@b.com", "password": "wrongpass1"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()  # same "invalid_credentials", no enumeration


def test_auth_error_bodies_do_not_leak_secrets(client):
    h = _auth(client)
    tok = h["Authorization"].split(" ", 1)[1]
    r = client.get("/auth/me", headers={"Authorization": "Bearer garbage.token"})
    assert r.status_code == 401
    # The valid token must never appear in an error body.
    assert tok not in r.text


# ---------------------------------------------------------------- API key lifecycle
def test_api_key_full_lifecycle_create_display_use_revoke_reuse(client):
    from batman.adapters_http import HTTPModelAdapter

    h, p, m, created = _onboard(client)
    raw = created["api_key"]
    key_id = created["key_id"]
    assert raw.startswith("bm_live_")

    # display-once: the raw key is NOT returned by the list endpoint
    listed = client.get("/keys", headers=h).json()["api_keys"]
    assert all("api_key" not in k and "key_hash" not in k for k in listed)
    assert not any(raw in str(k) for k in listed)

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        # use: the key works on the data plane
        ok = client.post("/v1/predict", json={"inputs": [[0.1, 0.2]], "session_id": "s"},
                         headers={"x-api-key": raw})
        assert ok.status_code == 200

        # revoke
        assert client.delete(f"/keys/{key_id}", headers=h).status_code == 200

        # reuse denied
        denied = client.post("/v1/predict", json={"inputs": [[0.1, 0.2]]},
                             headers={"x-api-key": raw})
        assert denied.status_code == 401
    finally:
        HTTPModelAdapter.predict = orig


def test_expired_api_key_denied(client):
    from batman.adapters_http import HTTPModelAdapter

    h = _auth(client, "kexp@b.com")
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(f"/models/{m['model_id']}/upstream", json={"url": "http://u.test/predict"}, headers=h)
    # Mint a key that expired in the past.
    past = "2000-01-01T00:00:00+00:00"
    raw = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"], "expires_at": past},
                      headers=h).json()["api_key"]

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        r = client.post("/v1/predict", json={"inputs": [[0.1]]}, headers={"x-api-key": raw})
        assert r.status_code == 401, "expired key must be rejected on the data plane"
    finally:
        HTTPModelAdapter.predict = orig


def test_invalid_and_missing_api_keys_denied(client):
    assert client.post("/v1/predict", json={"inputs": [[0.1]]}).status_code == 401  # missing
    assert client.post("/v1/predict", json={"inputs": [[0.1]]},
                       headers={"x-api-key": "bm_live_not_a_real_key"}).status_code == 401


def test_api_key_never_appears_in_telemetry_or_threat_detail(client):
    from batman.adapters_http import HTTPModelAdapter

    h, p, m, created = _onboard(client, "leak@b.com")
    raw = created["api_key"]
    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        rid = client.post("/v1/predict", json={"inputs": [[0.1, 0.2, 0.3]], "session_id": "s"},
                          headers={"x-api-key": raw}).json()["request_id"]
    finally:
        HTTPModelAdapter.predict = orig
    # The raw key must not be present in tenant telemetry or threat detail.
    threats = client.get("/v1/threats", headers=h).text
    assert raw not in threats
    detail = client.get(f"/v1/threats/{rid}", headers=h)
    if detail.status_code == 200:
        assert raw not in detail.text


# ---------------------------------------------------------------- input size bounds
def test_oversized_predict_row_count_rejected(client, monkeypatch):
    from batman.adapters_http import HTTPModelAdapter

    h, p, m, created = _onboard(client, "big@b.com")
    raw = created["api_key"]
    # Default cap is 1000 rows; send more.
    payload = {"inputs": [[0.1, 0.2] for _ in range(1001)], "session_id": "s"}
    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1] * len(inputs)
    try:
        r = client.post("/v1/predict", json=payload, headers={"x-api-key": raw})
        assert r.status_code == 413
    finally:
        HTTPModelAdapter.predict = orig


def test_oversized_predict_col_count_rejected(client):
    from batman.adapters_http import HTTPModelAdapter

    h, p, m, created = _onboard(client, "wide@b.com")
    raw = created["api_key"]
    # Default per-row cap is 4096 features.
    payload = {"inputs": [[0.0] * 4097], "session_id": "s"}
    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        r = client.post("/v1/predict", json=payload, headers={"x-api-key": raw})
        assert r.status_code == 413
    finally:
        HTTPModelAdapter.predict = orig


# ---------------------------------------------------------------- rate limiting
def test_signup_is_rate_limited(client):
    # The control-plane limiter has a burst cap; rapid repeated signups must
    # eventually be throttled with 429 rather than served without limit.
    statuses = []
    for i in range(40):
        r = client.post("/auth/signup", json={"email": f"rl{i}@b.com", "password": "password123"})
        statuses.append(r.status_code)
    assert 429 in statuses, "signup endpoint must be rate-limited"


def test_login_is_rate_limited(client):
    client.post("/auth/signup", json={"email": "rluser@b.com", "password": "password123"})
    statuses = []
    for _ in range(40):
        r = client.post("/auth/login", json={"email": "rluser@b.com", "password": "wrongpass9"})
        statuses.append(r.status_code)
    assert 429 in statuses, "login endpoint must be rate-limited"


def test_key_generation_is_rate_limited(client):
    h = _auth(client, "keyfarm@b.com")
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    statuses = []
    for _ in range(40):
        r = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h)
        statuses.append(r.status_code)
    assert 429 in statuses, "key generation must be rate-limited"


# ---------------------------------------------------------------- production config checks
def test_prodcheck_flags_insecure_production(monkeypatch):
    from batman.cloud.prodcheck import config_warnings

    monkeypatch.setenv("BATMAN_ENV", "production")
    monkeypatch.setenv("BATMAN_SECRET_KEY", "dev-insecure-secret-change-me")
    monkeypatch.delenv("BATMAN_ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("BATMAN_CORS_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")
    monkeypatch.setenv("BATMAN_DATABASE_URL", "sqlite:///batman.db")
    w = config_warnings()
    joined = " ".join(w)
    assert "BATMAN_SECRET_KEY" in joined
    assert "BATMAN_ENCRYPTION_KEY" in joined
    assert "BATMAN_CORS_ORIGINS" in joined
    assert "BATMAN_ALLOW_PRIVATE_UPSTREAM" in joined
    assert "BATMAN_DATABASE_URL" in joined


def test_prodcheck_clean_when_properly_configured(monkeypatch):
    from batman.cloud import crypto
    from batman.cloud.prodcheck import config_warnings

    monkeypatch.setenv("BATMAN_ENV", "production")
    monkeypatch.setenv("BATMAN_SECRET_KEY", "a-strong-unique-random-secret-value-1234567890")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_CORS_ORIGINS", "https://app.batman.example")
    monkeypatch.delenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", raising=False)
    monkeypatch.setenv("BATMAN_DATABASE_URL", "postgresql://u:p@db:5432/batman")
    assert config_warnings() == []
