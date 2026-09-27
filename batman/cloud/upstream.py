"""Resolve a stored UpstreamConfig into a live HTTPModelAdapter.

This is how BATMAN protects an already-deployed customer ML API: the per-model
config declares the upstream URL, request/response mapping, and (encrypted)
auth. We decrypt the credential only in-memory at call time to build request
headers, and reuse the Phase 1 ``HTTPModelAdapter`` for the actual proxying.

Credentials are never logged, never returned to clients, and only decrypted
transiently here.
"""

from __future__ import annotations

import numpy as np

from batman.adapters_http import HTTPModelAdapter
from batman.cloud import crypto
from batman.db.models import UpstreamConfig


def _build_request_builder(request_format: str):
    """Map BATMAN's numeric array to the upstream's request body shape."""
    if request_format == "raw":
        # Send a bare 2D list under "inputs".
        return lambda arr: {"inputs": np.asarray(arr, dtype=float).tolist()}
    # Default "instances": {"instances": [[...], ...]} (matches our ML service).
    return lambda arr: {"instances": np.asarray(arr, dtype=float).tolist()}


def _build_response_parser(response_format: str):
    """Extract predictions from the upstream response."""
    if response_format == "raw":
        return lambda payload: payload
    # Default: look for a "predictions" field, else return the whole payload.
    def parse(payload):
        if isinstance(payload, dict) and "predictions" in payload:
            return payload["predictions"]
        return payload
    return parse


def _auth_headers(cfg: UpstreamConfig) -> dict[str, str]:
    """Build upstream auth headers by transiently decrypting the stored secret."""
    if cfg.auth_type == "none" or not cfg.auth_secret_enc:
        return {}
    secret = crypto.decrypt_secret(cfg.auth_secret_enc)  # in-memory only
    if cfg.auth_type == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    if cfg.auth_type == "header":
        return {cfg.auth_header_name or "X-API-Key": secret}
    return {}


def _split_url(url: str, predict_path: str) -> tuple[str, str]:
    """Return (base_url, path).

    If ``url`` already ends with the predict path (a full endpoint URL was
    provided), split it; otherwise treat ``url`` as the base and use predict_path.
    """
    url = url.rstrip("/")
    if predict_path and url.endswith(predict_path.rstrip("/")):
        base = url[: -len(predict_path.rstrip("/"))].rstrip("/")
        return base or url, predict_path
    return url, predict_path


def adapter_from_config(cfg: UpstreamConfig) -> HTTPModelAdapter:
    base_url, path = _split_url(cfg.url, cfg.predict_path)
    return HTTPModelAdapter(
        base_url=base_url,
        predict_path=path,
        request_builder=_build_request_builder(cfg.request_format),
        response_parser=_build_response_parser(cfg.response_format),
        headers=_auth_headers(cfg),
        timeout=cfg.timeout_s,
    )
