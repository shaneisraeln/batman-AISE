"""Phase 2 end-to-end tests (in-process, CI-runnable).

Exercises the full productized journey using the REAL batman-ml SDK against the
in-process cloud app, with the upstream model mocked at the adapter boundary.

Covers:
  - SDK path: developer -> SDK -> cloud -> (mock) upstream -> real decision + prediction
  - Existing-API path: model registered with an upstream config, proxied
  - Security path: controlled extraction burst -> detection + enforcement
  - Tenant isolation, key revocation, upstream failure

The live variant (against real servers) lives in experiments/verify_cloud_e2e.py.
"""

import os
import tempfile

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.datasets import load_breast_cancer

from batman.cloud import crypto


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "e2e-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")
    # Use the breast-cancer detector so legit traffic isn't over-flagged.
    monkeypatch.setenv("BATMAN_DETECTOR_PATH", "models/isolation_forest_breast_cancer.joblib")


@pytest.fixture
def cloud():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from batman.cloud.app import create_cloud_app

    app = create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False)
    client = TestClient(app)
    yield client
    try:
        os.remove(path)
    except OSError:
        pass


def _sdk_bound_to(cloud_client: TestClient, api_key: str):
    """Return a real batman-ml BatmanClient whose transport targets the test app."""
    from batman_ml import BatmanClient

    sdk = BatmanClient(api_key=api_key, base_url="http://testserver")
    # Rebind the SDK's httpx client to the FastAPI test transport.
    sdk._client = httpx.Client(
        transport=cloud_client._transport,
        base_url="http://testserver",
        headers={"x-api-key": api_key},
    )
    return sdk


def _mock_upstream(prediction):
    """Patch HTTPModelAdapter.predict to return a deterministic upstream result."""
    from batman.adapters_http import HTTPModelAdapter

    orig = HTTPModelAdapter.predict
    HTTPModelAdapter.predict = lambda self, inputs: prediction
    return orig


def _restore_upstream(orig):
    from batman.adapters_http import HTTPModelAdapter

    HTTPModelAdapter.predict = orig


def _onboard(cloud, email="dev@example.com"):
    cloud.post("/auth/signup", json={"email": email, "password": "password123"})
    token = cloud.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    pid = cloud.post("/projects", json={"name": "P", "environment": "production"}, headers=H).json()["project_id"]
    mid = cloud.post("/models", json={"project_id": pid, "name": "m"}, headers=H).json()["model_id"]
    cloud.put(f"/models/{mid}/upstream", json={"url": "http://upstream.test/predict"}, headers=H)
    key = cloud.post("/keys", json={"project_id": pid, "model_id": mid}, headers=H).json()["api_key"]
    return H, pid, mid, key


def test_e2e_sdk_legit_prediction(cloud):
    H, pid, mid, key = _onboard(cloud)
    orig = _mock_upstream([0])
    try:
        sdk = _sdk_bound_to(cloud, key)
        sample = load_breast_cancer().data[0].tolist()
        result = sdk.predict([sample], session_id="sdk-normal")
        assert result.allowed
        assert result.prediction == [0]
        assert result.request_id
    finally:
        _restore_upstream(orig)


def test_e2e_security_extraction_enforced(cloud):
    H, pid, mid, key = _onboard(cloud)
    orig = _mock_upstream([1])
    try:
        sdk = _sdk_bound_to(cloud, key)
        data = load_breast_cancer().data
        lo, hi = data.min(0), data.max(0)
        rng = np.random.default_rng(5)
        actions = {}
        for _ in range(120):
            vec = (lo + (hi - lo) * rng.random(data.shape[1])).tolist()
            try:
                r = sdk.predict([vec], session_id="CTRL-extract")
                actions[r.action] = actions.get(r.action, 0) + 1
            except Exception as e:  # BlockedError surfaces here
                actions[type(e).__name__] = actions.get(type(e).__name__, 0) + 1
        enforced = sum(
            actions.get(k, 0) for k in ("BLOCK", "RATE_LIMIT", "BlockedError", "RateLimitedError")
        )
        assert enforced > 0, f"extraction never enforced: {actions}"
    finally:
        _restore_upstream(orig)


def test_e2e_tenant_isolation_of_telemetry(cloud):
    # Tenant A generates traffic; tenant B must not see A's metrics.
    Ha, pid_a, mid_a, key_a = _onboard(cloud, "a@example.com")
    orig = _mock_upstream([0])
    try:
        sdk_a = _sdk_bound_to(cloud, key_a)
        for _ in range(5):
            sdk_a.predict([load_breast_cancer().data[0].tolist()], session_id="a")
    finally:
        _restore_upstream(orig)

    Hb, *_ = _onboard(cloud, "b@example.com")
    metrics_b = cloud.get("/v1/metrics", headers=Hb).json()
    assert metrics_b["total_requests"] == 0  # B sees none of A's traffic

    metrics_a = cloud.get("/v1/metrics", headers=Ha).json()
    assert metrics_a["total_requests"] >= 5


def test_e2e_key_revocation_blocks_data_plane(cloud):
    H, pid, mid, key = _onboard(cloud)
    keys = cloud.get("/keys", headers=H).json()["api_keys"]
    cloud.delete(f"/keys/{keys[0]['key_id']}", headers=H)
    r = cloud.post("/v1/predict", headers={"x-api-key": key},
                   json={"inputs": [load_breast_cancer().data[0].tolist()]})
    assert r.status_code == 401


def test_e2e_upstream_failure_surfaces_as_upstream_error(cloud):
    H, pid, mid, key = _onboard(cloud)
    from batman.adapters_http import HTTPModelAdapter, MLServiceError

    orig = HTTPModelAdapter.predict

    def boom(self, inputs):
        raise MLServiceError("down")

    HTTPModelAdapter.predict = boom
    try:
        sdk = _sdk_bound_to(cloud, key)
        from batman_ml import UpstreamError

        with pytest.raises(UpstreamError):
            sdk.predict([load_breast_cancer().data[0].tolist()], session_id="s")
    finally:
        HTTPModelAdapter.predict = orig
