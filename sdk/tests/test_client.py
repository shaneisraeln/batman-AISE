"""Tests for the batman-ml client. Uses httpx MockTransport — no live server."""

import httpx
import pytest

from batman_ml import (
    AuthenticationError,
    BatmanClient,
    BlockedError,
    PredictionResult,
    ProtectedModel,
    RateLimitedError,
    ValidationError,
    protect,
)
from batman_ml.errors import ConnectionError as BatmanConnectionError
from batman_ml.errors import ServerError, TimeoutError as BatmanTimeout

KEY = "bm_live_testtokentokentoken"


def _client(handler, **kw):
    c = BatmanClient(api_key=KEY, base_url="http://batman.test", **kw)
    c._client = httpx.Client(base_url="http://batman.test", transport=httpx.MockTransport(handler),
                             headers={"x-api-key": KEY})
    return c


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("BATMAN_API_KEY", raising=False)
    with pytest.raises(AuthenticationError):
        BatmanClient(base_url="http://batman.test")


def test_rejects_malformed_key():
    with pytest.raises(AuthenticationError):
        BatmanClient(api_key="not-a-batman-key", base_url="http://batman.test")


def test_predict_success():
    def handler(request):
        assert request.headers["x-api-key"] == KEY
        return httpx.Response(200, json={
            "action": "LOG", "threat_type": "NONE", "threat_level": "LOW",
            "prediction": [1], "request_id": "req_abc", "latency_ms": 12.3,
        })

    c = _client(handler)
    r = c.predict([[1.0, 2.0, 3.0]])
    assert isinstance(r, PredictionResult)
    assert r.allowed and r.action == "LOG"
    assert r.prediction == [1]
    assert r.request_id == "req_abc"


def test_blocked_returns_result_by_default():
    def handler(request):
        return httpx.Response(200, json={
            "action": "BLOCK", "threat_type": "MODEL_EXTRACTION",
            "threat_level": "HIGH", "prediction": None, "request_id": "req_x",
        })

    c = _client(handler)
    r = c.predict([[1.0]])
    assert r.allowed is False and r.action == "BLOCK"


def test_blocked_raises_when_configured():
    def handler(request):
        return httpx.Response(200, json={"action": "BLOCK", "request_id": "r"})

    c = _client(handler, raise_on_block=True)
    with pytest.raises(BlockedError):
        c.predict([[1.0]])


def test_http_403_block_raises_blocked():
    def handler(request):
        return httpx.Response(403, json={"detail": {"message": "blocked", "action": "BLOCK"}})

    c = _client(handler)
    with pytest.raises(BlockedError):
        c.predict([[1.0]])


def test_401_raises_auth_error():
    c = _client(lambda r: httpx.Response(401, json={"detail": "unknown_key"}))
    with pytest.raises(AuthenticationError):
        c.predict([[1.0]])


def test_429_raises_rate_limited_with_retry_after():
    def handler(request):
        return httpx.Response(429, headers={"retry-after": "5"}, json={"detail": "slow down"})

    c = _client(handler)
    with pytest.raises(RateLimitedError) as ei:
        c.predict([[1.0]])
    assert ei.value.retry_after == 5.0


def test_422_raises_validation_error():
    c = _client(lambda r: httpx.Response(422, json={"detail": "bad shape"}))
    with pytest.raises(ValidationError):
        c.predict([[1.0]])


def test_500_retries_then_raises_server_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(500, json={"detail": "boom"})

    c = _client(handler, max_retries=2)
    with pytest.raises(ServerError):
        c.predict([[1.0]])
    assert calls["n"] == 3  # initial + 2 retries


def test_key_not_in_repr_or_errors():
    c = _client(lambda r: httpx.Response(200, json={"action": "LOG", "request_id": "r"}))
    r = c.predict([[1.0]])
    assert KEY not in repr(r)
    assert KEY not in repr(c)


def test_protect_wrapper_returns_prediction():
    def handler(request):
        return httpx.Response(200, json={"action": "ALLOW", "prediction": [0], "request_id": "r"})

    p = protect(api_key=KEY, base_url="http://batman.test")
    assert isinstance(p, ProtectedModel)
    p._client._client = httpx.Client(base_url="http://batman.test", transport=httpx.MockTransport(handler),
                                     headers={"x-api-key": KEY})
    assert p.predict([[1.0]]) == [0]


def test_numpy_inputs_supported_without_numpy_dep():
    np = pytest.importorskip("numpy")
    seen = {}

    def handler(request):
        import json
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"action": "LOG", "prediction": [1], "request_id": "r"})

    c = _client(handler)
    c.predict(np.array([[1.0, 2.0]]))
    assert seen["body"]["inputs"] == [[1.0, 2.0]]
