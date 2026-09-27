"""Unit tests for the HTTP model adapter (BATMAN proxying to an external ML API).

Uses httpx's MockTransport so no live server is required.
"""

import httpx
import numpy as np

from batman.adapters import ModelAdapter
from batman.adapters_http import HTTPModelAdapter, MLServiceError


def _adapter_with_handler(handler):
    a = HTTPModelAdapter(base_url="http://ml.test")
    a._client = httpx.Client(base_url="http://ml.test", transport=httpx.MockTransport(handler))
    return a


def test_adapter_is_a_model_adapter():
    assert issubclass(HTTPModelAdapter, ModelAdapter)


def test_predict_proxies_and_parses():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/predict"
        return httpx.Response(200, json={"predictions": [1, 0], "probabilities": [[0.1, 0.9], [0.8, 0.2]]})

    a = _adapter_with_handler(handler)
    out = a.predict(np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert out == [1, 0]


def test_predict_proba_returns_upstream_probabilities():
    def handler(request):
        return httpx.Response(200, json={"predictions": [1], "probabilities": [[0.2, 0.8]]})

    a = _adapter_with_handler(handler)
    proba = a.predict_proba(np.array([[1.0, 2.0]]))
    assert proba == [[0.2, 0.8]]


def test_upstream_error_raises():
    def handler(request):
        return httpx.Response(500, text="boom")

    a = _adapter_with_handler(handler)
    try:
        a.predict(np.array([[1.0]]))
        assert False, "expected MLServiceError"
    except MLServiceError as e:
        assert "upstream_status_500" in str(e)


def test_1d_input_reshaped():
    seen = {}

    def handler(request):
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"predictions": [1]})

    a = _adapter_with_handler(handler)
    a.predict(np.array([1.0, 2.0, 3.0]))
    assert seen["body"]["instances"] == [[1.0, 2.0, 3.0]]
