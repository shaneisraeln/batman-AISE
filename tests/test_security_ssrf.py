"""Phase 3 security audit — SSRF mitigation on upstream URLs.

BATMAN proxies inference to a tenant-supplied upstream URL. Without validation a
tenant could point it at loopback, private, link-local, or cloud-metadata
addresses. These tests pin the mitigation in batman/cloud/ssrf.py and its
enforcement in the /models/{id}/upstream endpoint.

By default (production posture) the private-range guard is ON. The
BATMAN_ALLOW_PRIVATE_UPSTREAM escape hatch (used for local dev / docker where
the model is on a private network) disables it.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from batman.cloud import crypto
from batman.cloud.ssrf import UpstreamURLError, validate_upstream_url


# ---------------------------------------------------------------- unit: guard ON
@pytest.fixture(autouse=True)
def _guard_on(monkeypatch):
    # Production posture: private upstreams are blocked.
    monkeypatch.delenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/predict",
        "http://127.0.0.1:9000/predict",
        "http://localhost:8100/predict",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/predict",                    # RFC1918
        "http://192.168.1.10/predict",                # RFC1918
        "http://172.16.0.9/predict",                  # RFC1918
        "http://[::1]/predict",                        # IPv6 loopback
        "http://0.0.0.0/predict",                      # unspecified
    ],
)
def test_blocked_addresses_rejected(url):
    with pytest.raises(UpstreamURLError):
        validate_upstream_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://example.com/x",
        "redis://127.0.0.1:6379",
    ],
)
def test_non_http_schemes_rejected(url):
    with pytest.raises(UpstreamURLError):
        validate_upstream_url(url)


def test_missing_host_rejected():
    with pytest.raises(UpstreamURLError):
        validate_upstream_url("http:///predict")


def test_public_host_allowed():
    # A well-known public host must pass (resolves to a public address).
    validate_upstream_url("https://example.com/predict")  # no raise


def test_unresolvable_host_rejected_when_guard_on():
    with pytest.raises(UpstreamURLError):
        validate_upstream_url("http://this-host-does-not-resolve.invalid/predict")


# ---------------------------------------------------------------- unit: guard OFF
def test_allow_private_env_permits_loopback(monkeypatch):
    monkeypatch.setenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", "1")
    validate_upstream_url("http://127.0.0.1:9000/predict")  # no raise
    validate_upstream_url("http://ml-service:9000/predict")  # docker service name


# ---------------------------------------------------------------- endpoint enforcement
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("BATMAN_SECRET_KEY", "ssrf-test-secret")
    monkeypatch.setenv("BATMAN_ENCRYPTION_KEY", crypto.generate_encryption_key())
    monkeypatch.setenv("BATMAN_LLM_PROVIDER", "stub")
    monkeypatch.delenv("BATMAN_ALLOW_PRIVATE_UPSTREAM", raising=False)  # guard ON
    from fastapi.testclient import TestClient
    from batman.cloud.app import create_cloud_app

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield TestClient(create_cloud_app(database_url=f"sqlite:///{path}", enable_llm=False))
    try:
        os.remove(path)
    except OSError:
        pass


def _auth(client, email="ssrf@b.com"):
    client.post("/auth/signup", json={"email": email, "password": "password123"})
    token = client.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_set_upstream_rejects_metadata_endpoint(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    r = client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "http://169.254.169.254/latest/meta-data/"},
        headers=h,
    )
    assert r.status_code == 400
    assert "upstream_url" in str(r.json()["detail"])


def test_set_upstream_rejects_loopback(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    r = client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "http://127.0.0.1:9000/predict"},
        headers=h,
    )
    assert r.status_code == 400


def test_set_upstream_allows_public_https(client):
    h = _auth(client)
    p = client.post("/projects", json={"name": "P"}, headers=h).json()
    m = client.post("/models", json={"project_id": p["project_id"], "name": "v1"}, headers=h).json()
    r = client.put(
        f"/models/{m['model_id']}/upstream",
        json={"url": "https://example.com/predict"},
        headers=h,
    )
    assert r.status_code == 200
