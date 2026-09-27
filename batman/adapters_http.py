"""HTTP model adapter — lets BATMAN proxy to a real, separately deployed ML API.

This is the seam that turns BATMAN from an in-process wrapper into a security
gateway sitting in front of an external model service. It implements the same
``ModelAdapter`` interface the engine already uses, so no engine, detector,
policy, or agent code changes.

The adapter maps BATMAN's numeric input array to the target service's request
schema, calls it over HTTP, and returns the parsed predictions. A configurable
request/response mapping keeps it honest: BATMAN does not pretend to understand
every arbitrary API — the format is declared explicitly.
"""

from __future__ import annotations

from typing import Any, Callable

import httpx
import numpy as np

from batman.adapters import ModelAdapter


class MLServiceError(Exception):
    """Raised when the upstream ML service returns an error or is unreachable."""


def _default_request_builder(arr: np.ndarray) -> dict:
    """Default: {"instances": [[...], ...]} — matches our Step-2 ML service."""
    return {"instances": np.asarray(arr, dtype=float).tolist()}


def _default_response_parser(payload: dict) -> Any:
    """Default: return the service's ``predictions`` list."""
    if isinstance(payload, dict) and "predictions" in payload:
        return payload["predictions"]
    return payload


class HTTPModelAdapter(ModelAdapter):
    """Proxy predictions to an external ML inference API.

    Args:
        base_url: e.g. ``http://localhost:9000``.
        predict_path: path of the prediction endpoint (default ``/predict``).
        request_builder: maps a numpy array to the service's request body.
        response_parser: maps the service's JSON response to predictions.
        headers: optional headers (e.g. upstream auth) forwarded to the service.
        timeout: per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        predict_path: str = "/predict",
        request_builder: Callable[[np.ndarray], dict] = _default_request_builder,
        response_parser: Callable[[dict], Any] = _default_response_parser,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.predict_path = predict_path
        self.request_builder = request_builder
        self.response_parser = response_parser
        self.headers = headers or {}
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, headers=self.headers
        )

    def predict(self, inputs: Any) -> Any:
        arr = np.asarray(inputs, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        body = self.request_builder(arr)
        try:
            resp = self._client.post(self.predict_path, json=body)
        except httpx.HTTPError as exc:
            raise MLServiceError(f"upstream_unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise MLServiceError(
                f"upstream_status_{resp.status_code}: {resp.text[:200]}"
            )
        return self.response_parser(resp.json())

    def predict_proba(self, inputs: Any) -> Any | None:
        """Return upstream probabilities if the service provides them."""
        arr = np.asarray(inputs, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        try:
            resp = self._client.post(self.predict_path, json=self.request_builder(arr))
            if resp.status_code >= 400:
                return None
            payload = resp.json()
            if isinstance(payload, dict) and "probabilities" in payload:
                return payload["probabilities"]
        except Exception:
            return None
        return None

    def health(self, health_path: str = "/health") -> bool:
        try:
            r = self._client.get(health_path)
            return r.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self._client.close()
