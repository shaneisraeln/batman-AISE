"""Integration tests: full pipeline through the engine/SDK and the gateway API."""

import numpy as np
import pytest
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from fastapi.testclient import TestClient

from batman import BATMAN
from batman.config import get_settings
from batman.engine import SecurityEngine
from batman.gateway.app import create_app
from batman.telemetry.store import TelemetryStore


@pytest.fixture
def victim_model():
    data = load_digits()
    return RandomForestClassifier(n_estimators=30, random_state=0).fit(
        data.data, data.target
    )


@pytest.fixture(autouse=True)
def isolated_db(tmp_db, monkeypatch):
    # Point the settings at a temp DB and clear the cache.
    monkeypatch.setenv("BATMAN_DB_PATH", tmp_db)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sdk_normal_traffic_allowed(victim_model):
    ref = load_digits().data.astype(float)
    shield = BATMAN(victim_model, api_key="bm_live_x", mode="enforce", enable_llm=False)
    r = shield.predict(ref[0:1], session_id="good")
    assert r.allowed
    assert r.prediction is not None


def test_sdk_extraction_blocked(victim_model):
    ref = load_digits().data.astype(float)
    shield = BATMAN(victim_model, api_key="bm_live_x", mode="enforce", enable_llm=False)
    rng = np.random.default_rng(1)
    lo, hi = ref.min(0), ref.max(0)
    last = None
    for _ in range(130):
        x = (lo + (hi - lo) * rng.random(ref.shape[1])).reshape(1, -1)
        last = shield.predict(x, session_id="attacker")
    assert last.action in ("BLOCK", "RATE_LIMIT")
    assert last.threat_type == "MODEL_EXTRACTION"


def test_monitor_mode_never_blocks(victim_model):
    ref = load_digits().data.astype(float)
    shield = BATMAN(victim_model, mode="monitor", enable_llm=False)
    rng = np.random.default_rng(2)
    lo, hi = ref.min(0), ref.max(0)
    for _ in range(120):
        x = (lo + (hi - lo) * rng.random(ref.shape[1])).reshape(1, -1)
        res = shield.predict(x, session_id="attacker2")
    # In monitor mode the request is always allowed (detect, don't block).
    assert res.allowed


def test_gateway_health_and_predict(victim_model):
    app = create_app(model=victim_model, enable_llm=False)
    client = TestClient(app)

    h = client.get("/v1/health")
    assert h.status_code == 200
    assert h.json()["status"] == "ok"

    ref = load_digits().data.astype(float)
    resp = client.post(
        "/v1/predict",
        json={"inputs": ref[0:1].tolist(), "session_id": "good"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "action" in body and "request_id" in body


def test_gateway_key_and_feedback_flow(victim_model):
    app = create_app(model=victim_model, enable_llm=False)
    client = TestClient(app)

    key = client.post("/v1/keys", json={"project_id": "p", "model_id": "m"}).json()
    assert key["api_key"].startswith("bm_live_")

    ref = load_digits().data.astype(float)
    r = client.post(
        "/v1/predict",
        headers={"x-api-key": key["api_key"]},
        json={"inputs": ref[0:1].tolist(), "session_id": "good"},
    )
    assert r.status_code == 200
    rid = r.json()["request_id"]

    fb = client.post(
        "/v1/feedback",
        json={"request_id": rid, "label": "TRUE_NEGATIVE", "analyst_note": "ok"},
    )
    assert fb.status_code == 200

    bad = client.post("/v1/feedback", json={"request_id": rid, "label": "BOGUS"})
    assert bad.status_code == 400


def test_gateway_bad_api_key_rejected(victim_model):
    app = create_app(model=victim_model, enable_llm=False)
    client = TestClient(app)
    ref = load_digits().data.astype(float)
    r = client.post(
        "/v1/predict",
        headers={"x-api-key": "bm_live_wrong"},
        json={"inputs": ref[0:1].tolist()},
    )
    assert r.status_code == 401
