"""Phase 3 security audit — CORS + upstream credential handling.

CORS:
  - never wildcard for a token-bearing API
  - allowed origins come from BATMAN_CORS_ORIGINS (config, not hardcoded)
  - a non-configured origin is not reflected in Access-Control-Allow-Origin
  - allow_credentials is safe because origins are always explicit (never '*')

Upstream credentials:
  - encrypted at rest (Fernet); plaintext never persisted
  - never returned in any API response (set/list)
  - not embedded in telemetry
  - decrypt round-trips only in memory
  - if encryption is unavailable, storing a secret fails closed (no plaintext)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "cors-test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")


def _make_app(monkeypatch, origins=None):
    from batman.cloud.app import create_cloud_app

    if origins is not None:
        monkeypatch.setenv("BATMAN_CORS_ORIGINS", origins)
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from fastapi.testclient import TestClient

    return TestClient(create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False)), path


def _cleanup(path):
    """Best-effort temp-DB removal. On Windows the SQLite file may still be
    held open by the app connection; a leftover temp file is harmless."""
    try:
        os.remove(path)
    except OSError:
        pass


def _auth(client, email="cu@b.com"):
    client.post("/auth/signup", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- CORS
def test_cors_never_wildcard(monkeypatch):
    from starlette.middleware.cors import CORSMiddleware

    client, path = _make_app(monkeypatch, "https://app.batman.example,https://batman.example")
    app = client.app
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware][0]
    origins = cors.kwargs.get("allow_origins")
    assert "*" not in origins
    assert cors.kwargs.get("allow_credentials") is True
    # credentials + wildcard is the dangerous combo; assert it never happens.
    assert not (cors.kwargs.get("allow_credentials") and "*" in origins)
    _cleanup(path)


def test_cors_allows_configured_origin(monkeypatch):
    client, path = _make_app(monkeypatch, "https://app.batman.example")
    r = client.get(
        "/v1/health",
        headers={"Origin": "https://app.batman.example", "Access-Control-Request-Method": "GET"},
    )
    # Starlette echoes the allowed origin back.
    assert r.headers.get("access-control-allow-origin") == "https://app.batman.example"
    _cleanup(path)


def test_cors_rejects_unconfigured_origin(monkeypatch):
    client, path = _make_app(monkeypatch, "https://app.batman.example")
    r = client.get("/v1/health", headers={"Origin": "https://evil.example"})
    # The evil origin must NOT be reflected as allowed.
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    _cleanup(path)


def test_cors_origins_come_from_config(monkeypatch):
    from starlette.middleware.cors import CORSMiddleware

    client, path = _make_app(monkeypatch, "https://only-this.example")
    cors = [m for m in client.app.user_middleware if m.cls is CORSMiddleware][0]
    assert cors.kwargs.get("allow_origins") == ["https://only-this.example"]
    _cleanup(path)


# ---------------------------------------------------------------- upstream credentials
def test_upstream_secret_encrypted_and_never_returned(monkeypatch):
    client, path = _make_app(monkeypatch, "http://localhost:5173")
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()

    secret = "sk-super-secret-upstream-token"
    r = client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "https://real-model.example/predict", "auth_type": "bearer", "auth_secret": secret},
        headers=h,
    )
    assert r.status_code == 200
    # The set response must NOT echo the secret.
    assert secret not in r.text
    assert "auth_secret" not in r.json()

    # Stored ciphertext must not contain the plaintext; decrypt round-trips.
    svc = client.app.state.service
    cfg = svc.get_upstream(m["model_id"])
    assert cfg.auth_secret_enc and secret not in cfg.auth_secret_enc
    assert crypto.decrypt_secret(cfg.auth_secret_enc) == secret

    # The models list must not surface the secret either.
    models = client.get("/models", headers=h)
    assert secret not in models.text
    _cleanup(path)


def test_upstream_secret_not_in_telemetry(monkeypatch):
    from batman.adapters_http import HTTPModelAdapter

    client, path = _make_app(monkeypatch, "http://localhost:5173")
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    secret = "sk-telemetry-leak-check"
    client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "https://real-model.example/predict", "auth_type": "bearer", "auth_secret": secret},
        headers=h,
    )
    key = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()["api_key"]

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        client.post("/v1/predict", json={"inputs": [[0.1, 0.2]], "session_id": "s"}, headers={"x-api-key": key})
    finally:
        HTTPModelAdapter.predict = orig

    # The upstream secret must never appear in tenant telemetry.
    assert secret not in client.get("/v1/threats", headers=h).text
    assert secret not in client.get("/v1/metrics", headers=h).text
    _cleanup(path)


def test_upstream_secret_fails_closed_without_encryption(monkeypatch):
    """If BATMAN_ENCRYPTION_KEY is unavailable, storing a secret must fail
    rather than persist plaintext (503, no silent plaintext write)."""
    monkeypatch.delenv("BATMAN_ENCRYPTION_KEY", raising=False)
    from batman.cloud.app import create_cloud_app
    from fastapi.testclient import TestClient

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    client = TestClient(create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False))
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    r = client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "https://x.example/predict", "auth_type": "bearer", "auth_secret": "leak-me"},
        headers=h,
    )
    assert r.status_code == 503, "must fail closed when encryption unavailable"
    # And no upstream config with a plaintext secret should have been written.
    svc = client.app.state.service
    cfg = svc.get_upstream(m["model_id"])
    assert cfg is None or (cfg.auth_secret_enc is None) or ("leak-me" not in (cfg.auth_secret_enc or ""))
    _cleanup(path)

