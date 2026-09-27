"""Tests for the hosted BATMAN cloud API (control plane + data plane)."""

import os
import tempfile

import httpx
import pytest
from fastapi.testclient import TestClient

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from batman.cloud.app import create_cloud_app

    app = create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False)
    yield TestClient(app)
    try:
        os.remove(path)
    except OSError:
        pass


def _auth(client, email="a@b.com", password="password123"):
    client.post("/auth/signup", json={"email": email, "password": password})
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_signup_login_me(client):
    h = _auth(client)
    me = client.get("/auth/me", headers=h)
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.com"


def test_protected_routes_require_token(client):
    assert client.get("/projects").status_code == 401
    assert client.get("/v1/metrics").status_code == 401


def test_full_control_plane_flow(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "Fraud", "environment": "production"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    key = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"], "name": "prod"}, headers=h).json()
    assert key["api_key"].startswith("bm_live_")

    listed = client.get("/keys", headers=h).json()["api_keys"]
    assert len(listed) == 1
    assert "api_key" not in listed[0] and "key_hash" not in listed[0]


def test_tenant_cannot_see_others_projects(client):
    h1 = _auth(client, "u1@b.com")
    h2 = _auth(client, "u2@b.com")
    client.post("/projects", json={"name": "u1proj"}, headers=h1)
    # u2 sees none of u1's projects
    assert client.get("/projects", headers=h2).json()["projects"] == []


def test_data_plane_predict_with_upstream(client):
    # Register a project/model, point it at a mock upstream, mint a key, predict.
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "http://upstream.test/predict", "auth_type": "none"},
        headers=h,
    )
    key = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()["api_key"]

    # Patch the upstream adapter's HTTP client to a mock so no real network call.
    import batman.cloud.app as cloud_app
    from batman.adapters_http import HTTPModelAdapter

    orig_predict = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]  # deterministic upstream
    try:
        r = client.post("/v1/predict", json={"inputs": [[0.1, 0.2, 0.3]], "session_id": "s1"},
                        headers={"x-api-key": key})
        assert r.status_code == 200
        body = r.json()
        assert body["prediction"] == [1]
        assert body["request_id"]
    finally:
        HTTPModelAdapter.predict = orig_predict


def test_data_plane_rejects_bad_key(client):
    r = client.post("/v1/predict", json={"inputs": [[0.1]]}, headers={"x-api-key": "bm_live_wrong"})
    assert r.status_code == 401


def test_revoked_key_denied(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    created = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()
    key, key_id = created["api_key"], created["key_id"]

    # revoke, then the data plane must reject it
    assert client.delete(f"/keys/{key_id}", headers=h).status_code == 200
    r = client.post("/v1/predict", json={"inputs": [[0.1]]}, headers={"x-api-key": key})
    assert r.status_code == 401


def test_metrics_are_tenant_scoped(client):
    h = _auth(client)
    # No traffic yet -> zeroed metrics, never another tenant's data.
    m = client.get("/v1/metrics", headers=h).json()
    assert m["total_requests"] == 0


def test_upstream_failure_returns_502(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "http://upstream.test/predict"},
        headers=h,
    )
    key = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()["api_key"]

    from batman.adapters_http import HTTPModelAdapter, MLServiceError

    orig = HTTPModelAdapter.predict

    def boom(self, inputs):
        raise MLServiceError("upstream_unreachable")

    HTTPModelAdapter.predict = boom
    try:
        r = client.post("/v1/predict", json={"inputs": [[0.1, 0.2]], "session_id": "s"},
                        headers={"x-api-key": key})
        assert r.status_code == 502
    finally:
        HTTPModelAdapter.predict = orig


def test_upstream_header_auth_encrypted_and_applied(client):
    """A custom-header upstream credential is encrypted at rest and sent to upstream."""
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(
        f"/models/{m['model_id']}/upstream",
        json={
            "url": "http://upstream.test/predict",
            "auth_type": "header",
            "auth_secret": "sekret-upstream",
            "auth_header_name": "X-Upstream-Token",
        },
        headers=h,
    )
    # The adapter built from config must carry the decrypted header.
    from batman.cloud.service import ControlPlaneService
    svc: ControlPlaneService = client.app.state.service
    cfg = svc.get_upstream(m["model_id"])
    assert cfg.auth_secret_enc and "sekret-upstream" not in cfg.auth_secret_enc

    from batman.cloud.upstream import adapter_from_config
    adapter = adapter_from_config(cfg)
    assert adapter.headers.get("X-Upstream-Token") == "sekret-upstream"
    adapter.close()


# ---------------- Phase 2B: Bearer feedback + tenant isolation + CORS ----------------
def _seed_threat(client, headers, api_key):
    """Drive one data-plane request so a telemetry row exists, return its request_id."""
    from batman.adapters_http import HTTPModelAdapter

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        r = client.post(
            "/v1/predict",
            json={"inputs": [[0.1, 0.2, 0.3]], "session_id": "fb"},
            headers={"x-api-key": api_key},
        )
        return r.json()["request_id"]
    finally:
        HTTPModelAdapter.predict = orig


def _onboard_with_key(client, email="fb@b.com"):
    h = _auth(client, email)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(f"/models/{m['model_id']}/upstream", json={"url": "http://u.test/predict"}, headers=h)
    key = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()["api_key"]
    return h, key


def test_bearer_feedback_records_and_lists(client):
    h, key = _onboard_with_key(client)
    rid = _seed_threat(client, h, key)
    # Submit feedback via the dashboard (Bearer) endpoint.
    r = client.post("/v1/feedback", json={"request_id": rid, "label": "TRUE_POSITIVE", "analyst_note": "looks real"}, headers=h)
    assert r.status_code == 200
    # It appears in the tenant-scoped feedback list.
    fb = client.get("/v1/feedback", headers=h).json()["feedback"]
    assert any(f["request_id"] == rid and f["label"] == "TRUE_POSITIVE" for f in fb)


def test_threat_detail_returns_prior_feedback(client):
    """The dashboard ThreatDetail view re-fetches /v1/threats/{id} after
    submitting a verdict and shows d.feedback. Verify the detail endpoint
    actually returns the recorded feedback for the same tenant."""
    h, key = _onboard_with_key(client)
    rid = _seed_threat(client, h, key)
    client.post("/v1/feedback", json={"request_id": rid, "label": "FALSE_POSITIVE", "analyst_note": "benign"}, headers=h)
    detail = client.get(f"/v1/threats/{rid}", headers=h)
    assert detail.status_code == 200
    body = detail.json()
    assert body["request_id"] == rid
    assert any(f["label"] == "FALSE_POSITIVE" for f in body.get("feedback", []))


def test_bearer_feedback_invalid_label(client):
    h, key = _onboard_with_key(client)
    rid = _seed_threat(client, h, key)
    r = client.post("/v1/feedback", json={"request_id": rid, "label": "NOPE"}, headers=h)
    assert r.status_code == 400


def test_feedback_requires_auth(client):
    r = client.post("/v1/feedback", json={"request_id": "req_x", "label": "TRUE_POSITIVE"})
    assert r.status_code == 401


def test_cannot_feedback_on_another_tenants_threat(client):
    ha, key_a = _onboard_with_key(client, "owner@b.com")
    rid = _seed_threat(client, ha, key_a)
    # A different tenant must not be able to submit feedback on A's threat.
    hb = _auth(client, "intruder@b.com")
    r = client.post("/v1/feedback", json={"request_id": rid, "label": "FALSE_POSITIVE"}, headers=hb)
    assert r.status_code == 404
    # And B's feedback list stays empty.
    assert client.get("/v1/feedback", headers=hb).json()["feedback"] == []


def test_cors_origins_are_not_wildcard(monkeypatch):
    """CORS must be explicit origins, never '*', for a token-bearing API."""
    monkeypatch.setenv("BATMAN_SECRET_KEY", "test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_CORS_ORIGINS", "https://app.batman.example,https://batman.example")
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from batman.cloud.app import create_cloud_app
    from starlette.middleware.cors import CORSMiddleware

    app = create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False)
    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert cors, "CORS middleware not configured"
    origins = cors[0].kwargs.get("allow_origins")
    assert "*" not in origins
    assert "https://app.batman.example" in origins
    try:
        os.remove(path)
    except OSError:
        pass
