"""BATMAN client — a thin HTTP wrapper around the hosted BATMAN API.

Design goals:
  - lightweight: only depends on httpx (no engine, sklearn, numpy required)
  - safe: the API key is sent only in the ``x-api-key`` header, never logged
  - explicit: HTTP outcomes map to a typed exception hierarchy
  - ergonomic: ``protect(model, api_key, base_url).predict(X)``

Two usage styles:
  1. Gateway/hosted (default): BATMAN proxies to a model you registered in the
     dashboard. ``predict(X)`` sends inputs to BATMAN, which runs detection,
     applies policy, calls your upstream model, and returns the prediction.
  2. Analyze-only: ``analyze(X)`` runs detection/policy without returning a
     model prediction (useful for shadow/monitor deployments).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import httpx

from batman_ml._version import __version__
from batman_ml.errors import (
    AuthenticationError,
    AuthorizationError,
    BatmanError,
    BlockedError,
    ConnectionError,
    RateLimitedError,
    ServerError,
    TimeoutError,
    UpstreamError,
    ValidationError,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
KEY_PREFIX = "bm_live_"


def _to_list(x: Any) -> list:
    """Coerce inputs to a JSON-serializable nested list without requiring numpy."""
    if hasattr(x, "tolist"):  # numpy array / pandas without importing them
        return x.tolist()
    if isinstance(x, (list, tuple)):
        return [_to_list(v) if isinstance(v, (list, tuple)) or hasattr(v, "tolist") else v for v in x]
    return x


def _redact(key: str | None) -> str:
    if not key:
        return "<none>"
    return f"{key[:11]}…" if len(key) > 12 else "<redacted>"


@dataclass
class PredictionResult:
    """Result of a protected prediction."""

    allowed: bool
    action: str
    threat_type: str
    threat_level: str
    prediction: Any
    request_id: str
    latency_ms: float
    raw: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # never expose keys; safe summary
        return (
            f"PredictionResult(action={self.action!r}, allowed={self.allowed}, "
            f"threat_type={self.threat_type!r}, request_id={self.request_id!r})"
        )


class BatmanClient:
    """Client for the hosted BATMAN API.

    Args:
        api_key: BATMAN key (``bm_live_...``). May also be set via BATMAN_API_KEY.
        base_url: BATMAN API base URL. May also be set via BATMAN_BASE_URL.
        timeout: per-request timeout in seconds.
        max_retries: retries for transient network/5xx errors (idempotent calls).
        raise_on_block: if True, a BLOCK decision raises BlockedError instead of
            returning a result with ``allowed=False``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 2,
        raise_on_block: bool = False,
    ):
        self._api_key = api_key or os.getenv("BATMAN_API_KEY")
        self.base_url = (base_url or os.getenv("BATMAN_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.raise_on_block = raise_on_block

        if not self._api_key:
            raise AuthenticationError(
                "No API key provided. Pass api_key= or set BATMAN_API_KEY."
            )
        if not self._api_key.startswith(KEY_PREFIX):
            raise AuthenticationError(
                f"API key must start with {KEY_PREFIX!r} (got {_redact(self._api_key)})."
            )

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "x-api-key": self._api_key,
                "user-agent": f"batman-ml/{__version__}",
            },
        )

    # --- public API ---
    def predict(self, inputs: Any, session_id: str | None = None) -> PredictionResult:
        """Send inputs through BATMAN to the protected model and return the result."""
        body = {"inputs": _to_list(inputs)}
        if session_id:
            body["session_id"] = session_id
        data = self._post("/v1/predict", body)
        result = self._parse_prediction(data)
        if self.raise_on_block and result.action == "BLOCK":
            raise BlockedError("Request blocked by BATMAN policy.", data)
        return result

    def analyze(self, inputs: Any, session_id: str | None = None) -> PredictionResult:
        """Run detection/policy without returning a model prediction."""
        body = {"inputs": _to_list(inputs), "analyze_only": True}
        if session_id:
            body["session_id"] = session_id
        data = self._post("/v1/predict", body)
        return self._parse_prediction(data)

    def health(self) -> dict:
        """Return the BATMAN API health payload."""
        return self._get("/v1/health")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BatmanClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- internals ---
    def _parse_prediction(self, data: dict) -> PredictionResult:
        return PredictionResult(
            allowed=data.get("action") in ("ALLOW", "LOG"),
            action=data.get("action", "UNKNOWN"),
            threat_type=data.get("threat_type", "NONE"),
            threat_level=data.get("threat_level", "NONE"),
            prediction=data.get("prediction"),
            request_id=data.get("request_id", ""),
            latency_ms=float(data.get("latency_ms", 0.0) or 0.0),
            raw=data,
        )

    def _get(self, path: str) -> dict:
        return self._request("GET", path, None)

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, body)

    def _request(self, method: str, path: str, body: dict | None) -> dict:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.request(method, path, json=body)
            except httpx.TimeoutException as exc:
                last_exc = TimeoutError(f"BATMAN request timed out after {self.timeout}s")
                continue  # retry transient timeout
            except httpx.HTTPError as exc:
                last_exc = ConnectionError(f"Could not reach BATMAN at {self.base_url}")
                continue  # retry transient network error

            # Retry only on transient 5xx.
            if resp.status_code >= 500 and attempt < self.max_retries:
                last_exc = ServerError(f"BATMAN server error (HTTP {resp.status_code})")
                continue
            return self._handle_response(resp)

        assert last_exc is not None
        raise last_exc

    def _handle_response(self, resp: httpx.Response) -> dict:
        code = resp.status_code
        if code == 200:
            return resp.json()

        detail = self._safe_detail(resp)
        if code == 401:
            raise AuthenticationError("Invalid or missing BATMAN API key.")
        if code == 403:
            # BATMAN returns 403 for policy BLOCK (with a decision) and for authz.
            if isinstance(detail, dict) and detail.get("message") == "blocked":
                raise BlockedError("Request blocked by BATMAN policy.", detail)
            raise AuthorizationError("Not authorized for this resource.")
        if code == 429:
            retry_after = None
            try:
                retry_after = float(resp.headers.get("retry-after", "")) or None
            except ValueError:
                pass
            raise RateLimitedError("Rate limited by BATMAN.", retry_after)
        if code in (400, 422):
            raise ValidationError(f"Invalid request payload: {detail}")
        if code in (502, 504):
            raise UpstreamError("Protected upstream model/API failed.")
        if code >= 500:
            raise ServerError(f"BATMAN server error (HTTP {code}).")
        raise BatmanError(f"Unexpected BATMAN response (HTTP {code}): {detail}")

    @staticmethod
    def _safe_detail(resp: httpx.Response) -> Any:
        try:
            data = resp.json()
            return data.get("detail", data) if isinstance(data, dict) else data
        except Exception:
            return resp.text[:200]


class ProtectedModel:
    """A drop-in wrapper returned by :func:`protect`.

    Exposes ``.predict(X)`` so it can stand in for a model object in existing
    code, while routing inference through BATMAN.
    """

    def __init__(self, client: BatmanClient, session_id: str | None = None):
        self._client = client
        self._session_id = session_id

    def predict(self, X: Any) -> Any:
        """Return the model's prediction (raises on BLOCK if configured)."""
        result = self._client.predict(X, session_id=self._session_id)
        return result.prediction

    def predict_secure(self, X: Any) -> PredictionResult:
        """Return the full BATMAN result (decision + prediction)."""
        return self._client.predict(X, session_id=self._session_id)

    def close(self) -> None:
        self._client.close()


def protect(
    model: Any = None,
    api_key: str | None = None,
    base_url: str | None = None,
    session_id: str | None = None,
    timeout: float = 30.0,
    raise_on_block: bool = False,
) -> ProtectedModel:
    """Protect a model's inference through BATMAN.

    In the hosted model, the model itself lives behind the BATMAN API (registered
    in the dashboard), so ``model`` is typically ``None`` here and inference is
    routed to your registered upstream. The ``model`` parameter is accepted for
    API symmetry and future embedded modes; it is not sent anywhere.

    Example::

        from batman_ml import protect
        protected = protect(api_key="bm_live_xxx", base_url="https://api.batman.example")
        prediction = protected.predict(X)
    """
    client = BatmanClient(
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        raise_on_block=raise_on_block,
    )
    return ProtectedModel(client, session_id=session_id)
