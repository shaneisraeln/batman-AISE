"""Automated full-funnel E2E: a brand-new developer's complete journey.

This drives the real cloud app (control plane + data plane) through the entire
self-serve funnel with NO manual database edits and NO running services — the
only thing stubbed is the upstream model HTTP call (so we don't need a live
ml-service). It is the automated counterpart to experiments/verify_cloud_e2e.py.

Funnel covered:
    signup -> login -> create project -> register model -> configure upstream
    -> mint API key -> SDK-shaped predict (real prediction proxied)
    -> controlled extraction burst -> detection/enforcement + telemetry
    -> analyst feedback (record + list + attach to detail)
    -> revoke key -> revoked key denied (401)
    -> logout (token discard) -> protected route unreachable (401)
"""

from __future__ import annotations

import os
import tempfile

import pytest

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "e2e-secret")
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


def _diverse_vectors(n: int, dims: int = 30):
    """Deterministic, high-diversity feature vectors to simulate systematic
    probing (the behavioral signature of model extraction)."""
    import random

    rng = random.Random(1234)
    return [[rng.uniform(-3.0, 3.0) for _ in range(dims)] for _ in range(n)]


def test_full_developer_funnel(client):
    # --- 1) signup + login ---
    email = "founder@newco.example"
    signup = client.post("/auth/signup", json={"email": email, "password": "password123", "display_name": "Founder"})
    assert signup.status_code == 200
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    assert client.get("/auth/me", headers=H).json()["email"] == email

    # --- 2) project + model + upstream ---
    pid = client.post("/projects", json={"name": "Diagnostics", "environment": "production"}, headers=H).json()["project_id"]
    mid = client.post("/models", json={"project_id": pid, "name": "cancer-v1"}, headers=H).json()["model_id"]
    up = client.put(f"/models/{mid}/upstream", json={"url": "http://upstream.test/predict"}, headers=H)
    assert up.status_code == 200

    # --- 3) mint API key ---
    created = client.post("/keys", json={"project_id": pid, "model_id": mid, "name": "sdk"}, headers=H).json()
    key, key_id = created["api_key"], created["key_id"]
    assert key.startswith("bm_live_")

    # Stub the upstream model so predict returns a deterministic prediction.
    from batman.adapters_http import HTTPModelAdapter

    orig_predict = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: [1] * len(inputs)
    try:
        # --- 4) a legitimate request returns a real (proxied) prediction ---
        legit = client.post(
            "/v1/predict",
            json={"inputs": [_diverse_vectors(1)[0]], "session_id": "normal-1"},
            headers={"x-api-key": key},
        )
        assert legit.status_code == 200
        body = legit.json()
        assert body["prediction"] is not None
        assert body["request_id"]

        # --- 5) controlled extraction burst -> detection / enforcement ---
        actions = {}
        for vec in _diverse_vectors(150):
            r = client.post(
                "/v1/predict",
                json={"inputs": [vec], "session_id": "CTRL-extract"},
                headers={"x-api-key": key},
            )
            if r.status_code == 200:
                a = r.json()["action"]
            elif r.status_code == 403:
                a = "BLOCK"
            else:
                a = f"HTTP_{r.status_code}"
            actions[a] = actions.get(a, 0) + 1
        # The burst must have been detected/enforced in some form.
        assert any(a in actions for a in ("BLOCK", "RATE_LIMIT", "ESCALATE")), actions
    finally:
        HTTPModelAdapter.predict = orig_predict

    # --- 6) tenant-scoped telemetry reflects the traffic ---
    metrics = client.get("/v1/metrics", headers=H).json()
    assert metrics["total_requests"] >= 1
    threats = client.get("/v1/threats?limit=50", headers=H).json()["threats"]
    assert len(threats) >= 1

    # --- 7) analyst feedback: label a detected threat, confirm list + detail ---
    rid = threats[0]["request_id"]
    fb = client.post(
        "/v1/feedback",
        json={"request_id": rid, "label": "TRUE_POSITIVE", "analyst_note": "e2e"},
        headers=H,
    )
    assert fb.status_code == 200
    listed = client.get("/v1/feedback", headers=H).json()["feedback"]
    assert any(f["request_id"] == rid and f["label"] == "TRUE_POSITIVE" for f in listed)
    detail = client.get(f"/v1/threats/{rid}", headers=H).json()
    assert any(f["label"] == "TRUE_POSITIVE" for f in detail.get("feedback", []))

    # --- 8) revoke the key -> the data plane denies it ---
    assert client.delete(f"/keys/{key_id}", headers=H).status_code == 200
    denied = client.post("/v1/predict", json={"inputs": [_diverse_vectors(1)[0]]}, headers={"x-api-key": key})
    assert denied.status_code == 401

    # --- 9) logout is a client-side token discard; without a token, protected
    #        control-plane routes are unreachable. ---
    assert client.get("/v1/metrics").status_code == 401
    assert client.get("/projects").status_code == 401


def test_new_tenant_sees_no_prior_data(client):
    """A second brand-new developer must start with a clean, isolated slate."""
    # First tenant generates some state.
    client.post("/auth/signup", json={"email": "one@x.example", "password": "password123"})
    t1 = client.post("/auth/login", json={"email": "one@x.example", "password": "password123"}).json()["token"]
    H1 = {"Authorization": f"Bearer {t1}"}
    client.post("/projects", json={"name": "Owned"}, headers=H1)

    # Second tenant signs up fresh.
    client.post("/auth/signup", json={"email": "two@x.example", "password": "password123"})
    t2 = client.post("/auth/login", json={"email": "two@x.example", "password": "password123"}).json()["token"]
    H2 = {"Authorization": f"Bearer {t2}"}

    assert client.get("/projects", headers=H2).json()["projects"] == []
    assert client.get("/keys", headers=H2).json()["api_keys"] == []
    assert client.get("/v1/metrics", headers=H2).json()["total_requests"] == 0
    assert client.get("/v1/feedback", headers=H2).json()["feedback"] == []
