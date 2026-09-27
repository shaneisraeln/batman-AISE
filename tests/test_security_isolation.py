"""Phase 3 security audit — adversarial tenant-isolation tests.

Two tenants (A = victim, B = attacker) are created. B then attempts, using B's
own valid bearer token and B's own valid API key, to read or mutate every kind
of resource that belongs to A:

    projects, models, API keys, telemetry, threats (list + detail),
    analyst feedback, upstream configuration.

Every cross-tenant attempt MUST be DENIED (404/empty/no-op). No resource that
belongs to A may ever be returned to, or mutated by, B.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "iso-test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    # Tests use mock/private upstream hosts; allow them past the SSRF guard.
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


def _auth(client, email):
    client.post("/auth/signup", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _full_tenant(client, email, session="s"):
    """Create project+model+upstream+key and drive one predict so a telemetry
    row exists. Returns a dict of all of A's identifiers + a request_id."""
    from batman.adapters_http import HTTPModelAdapter

    h = _auth(client, email)
    p = client.post("/projects", json={"name": "Victim"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    client.put(f"/models/{m['model_id']}/upstream", json={"url": "http://upstream.test/predict"}, headers=h)
    created = client.post("/keys", json={"project_id": p["project_id"], "model_id": m["model_id"]}, headers=h).json()

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        rid = client.post("/v1/predict", json={"inputs": [[0.1, 0.2, 0.3]], "session_id": session},
                          headers={"x-api-key": created["api_key"]}).json()["request_id"]
    finally:
        HTTPModelAdapter.predict = orig
    # Record analyst feedback so A has a feedback row too.
    client.post("/v1/feedback", json={"request_id": rid, "label": "TRUE_POSITIVE"}, headers=h)
    return {
        "h": h, "project_id": p["project_id"], "model_id": m["model_id"],
        "key_id": created["key_id"], "api_key": created["api_key"], "request_id": rid,
    }


@pytest.fixture
def victim_and_attacker(client):
    a = _full_tenant(client, "victim@a.com")
    hb = _auth(client, "attacker@b.com")
    return a, hb


# ---------------------------------------------------------------- projects
def test_attacker_cannot_list_victim_projects(client, victim_and_attacker):
    a, hb = victim_and_attacker
    # B lists only B's projects (none).
    resp = client.get("/projects", headers=hb)
    assert resp.status_code == 200
    assert resp.json()["projects"] == []


# ---------------------------------------------------------------- models
def test_attacker_cannot_register_model_under_victim_project(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.post("/models", json={"project_id": a["project_id"], "name": "evil"}, headers=hb)
    assert r.status_code == 404


def test_attacker_cannot_list_victim_models_by_project_id(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.get(f"/models?project_id={a['project_id']}", headers=hb)
    assert r.status_code == 404  # project_not_found (not owned)


# ---------------------------------------------------------------- API keys
def test_attacker_cannot_create_key_under_victim_model(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.post("/keys", json={"project_id": a["project_id"], "model_id": a["model_id"]}, headers=hb)
    assert r.status_code == 404


def test_attacker_cannot_revoke_victim_key(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.delete(f"/keys/{a['key_id']}", headers=hb)
    assert r.status_code == 404  # not owned -> no-op -> key_not_found

    # And A's key must still work after B's attempted revoke.
    from batman.adapters_http import HTTPModelAdapter
    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1]
    try:
        ok = client.post("/v1/predict", json={"inputs": [[0.1]]}, headers={"x-api-key": a["api_key"]})
        assert ok.status_code == 200
    finally:
        HTTPModelAdapter.predict = orig


def test_attacker_key_list_excludes_victim_keys(client, victim_and_attacker):
    a, hb = victim_and_attacker
    keys = client.get("/keys", headers=hb).json()["api_keys"]
    assert all(k["key_id"] != a["key_id"] for k in keys)
    assert keys == []


# ---------------------------------------------------------------- upstream config
def test_attacker_cannot_configure_victim_upstream(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.put(f"/models/{a['model_id']}/upstream",
                   json={"url": "http://attacker.example/steal"}, headers=hb)
    assert r.status_code == 404


# ---------------------------------------------------------------- telemetry / threats
def test_attacker_metrics_are_empty(client, victim_and_attacker):
    a, hb = victim_and_attacker
    m = client.get("/v1/metrics", headers=hb).json()
    assert m["total_requests"] == 0


def test_attacker_threats_list_is_empty(client, victim_and_attacker):
    a, hb = victim_and_attacker
    t = client.get("/v1/threats", headers=hb).json()["threats"]
    assert t == []


def test_attacker_cannot_read_victim_threat_detail(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.get(f"/v1/threats/{a['request_id']}", headers=hb)
    assert r.status_code == 404


# ---------------------------------------------------------------- feedback
def test_attacker_cannot_feedback_on_victim_threat(client, victim_and_attacker):
    a, hb = victim_and_attacker
    r = client.post("/v1/feedback", json={"request_id": a["request_id"], "label": "FALSE_POSITIVE"}, headers=hb)
    assert r.status_code == 404


def test_attacker_feedback_list_is_empty(client, victim_and_attacker):
    a, hb = victim_and_attacker
    fb = client.get("/v1/feedback", headers=hb).json()["feedback"]
    assert fb == []


# ---------------------------------------------------------------- data-plane cross-key
def test_attacker_api_key_cannot_feedback_on_victim_request(client, victim_and_attacker):
    """B's own API key (data plane) must not label A's telemetry row."""
    a, hb = victim_and_attacker
    # Give B a full project/model/key.
    pb = client.post("/projects", json={"name": "B"}, headers=hb).json()
    mb = client.post("/models", json={"project_id": pb["project_id"], "name": "bm"}, headers=hb).json()
    client.put(f"/models/{mb['model_id']}/upstream", json={"url": "http://u.test/predict"}, headers=hb)
    bkey = client.post("/keys", json={"project_id": pb["project_id"], "model_id": mb["model_id"]}, headers=hb).json()["api_key"]
    # B tries the data-plane feedback endpoint against A's request_id.
    r = client.post(f"/v1/data/feedback?request_id={a['request_id']}&label=FALSE_POSITIVE",
                    headers={"x-api-key": bkey})
    assert r.status_code == 404
