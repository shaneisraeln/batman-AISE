"""Hosted BATMAN API — control plane + multi-tenant data plane.

Control plane (Bearer-token auth):
    POST /auth/signup, POST /auth/login
    GET/POST /projects
    GET/POST /models
    GET/POST /keys, DELETE /keys/{key_id}
    PUT /models/{model_id}/upstream
    GET /v1/threats, GET /v1/metrics   (tenant-scoped)

Data plane (API-key auth via x-api-key):
    POST /v1/predict
    POST /v1/feedback
    GET  /v1/health

Design notes preserving Phase 1:
  - Detection uses the SAME SecurityEngine (no detector duplication).
  - The engine runs detection with run_model=False; the resolved per-model
    upstream adapter is invoked ONLY when the decision allows, so blocked
    requests never reach the model — and this stays thread-safe under load.
  - The policy engine remains authoritative; the LLM stays advisory.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from batman.adapters_http import MLServiceError
from batman.cloud.schemas import (
    CreateKeyRequest,
    CreateProjectRequest,
    FeedbackRequest,
    LoginRequest,
    PredictRequest,
    RegisterModelRequest,
    SignupRequest,
    TokenResponse,
    UpstreamRequest,
)
from batman.cloud.service import ControlPlaneService, ServiceError
from batman.cloud.upstream import adapter_from_config
from batman.config import get_settings
from batman.db.database import Database
from batman.engine import SecurityEngine
from batman.gateway.auth import AuthError, hash_key, is_expired
from batman.gateway.rate_limit import SlidingWindowRateLimiter
from batman.telemetry.schema import VALID_FEEDBACK_LABELS, FeedbackRecord
from batman.telemetry.store import TelemetryStore
from batman.types import Action


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_cloud_app(database_url: str | None = None, enable_llm: bool = False) -> FastAPI:
    settings = get_settings()
    db = Database(database_url) if database_url else Database()
    service = ControlPlaneService(db)

    # Reuse the Phase 1 store (bound to the SAME database) + the Phase 1 engine
    # for detection. model=None: the data plane invokes per-model upstreams.
    store = TelemetryStore(url=db.url)
    detector_path = os.getenv("BATMAN_DETECTOR_PATH", "models/isolation_forest.joblib")
    engine = SecurityEngine(
        model=None, settings=settings, store=store,
        detector_path=detector_path, enable_llm=enable_llm,
    )

    # A dedicated limiter for control-plane auth endpoints (anti-bruteforce).
    from batman.config import RateLimitConfig

    control_limiter = SlidingWindowRateLimiter(RateLimitConfig(requests_per_minute=30, burst=8))

    app = FastAPI(title="BATMAN Cloud API", version="2.0.0")
    # CORS locked to explicit origins (never wildcard for a token-bearing API).
    # Configure via BATMAN_CORS_ORIGINS (comma-separated); dev default is localhost.
    cors_origins = [
        o.strip()
        for o in os.getenv(
            "BATMAN_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "x-api-key"],
    )
    app.state.service = service
    app.state.engine = engine
    app.state.store = store

    # Advisory production-readiness checks (logged, never hard-fail here).
    from batman.cloud.prodcheck import config_warnings
    from batman.telemetry.logger import get_logger

    _startup_logger = get_logger("batman.cloud", settings.log_level)
    for _w in config_warnings():
        _startup_logger.warning(_w)

    # ---------------- auth dependencies ----------------
    def current_user(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        token = authorization.split(" ", 1)[1].strip()
        user = service.user_from_token(token)
        if not user:
            raise HTTPException(status_code=401, detail="invalid_or_expired_token")
        return user

    def authenticate_api_key(x_api_key: str | None = Header(default=None)):
        """Resolve an API key to its (project_id, model_id, key_id). Data plane."""
        if not x_api_key:
            raise HTTPException(status_code=401, detail="missing_api_key")
        record = service.keys.get_by_hash(hash_key(x_api_key))
        # Reject unknown, revoked, or (optionally) expired keys. Expiry is
        # enforced here as well as at status level so a key with a past
        # expires_at cannot be used even while still marked active.
        if record is None or record.status != "active" or is_expired(record):
            raise HTTPException(status_code=401, detail="invalid_or_revoked_key")
        # Update last-used (best effort).
        try:
            service.keys.touch_last_used(record.key_id, _now())
        except Exception:
            pass
        return record

    # ---------------- auth endpoints ----------------
    @app.post("/auth/signup", response_model=TokenResponse)
    def signup(req: SignupRequest):
        _throttle_control(control_limiter, "signup")
        try:
            user = service.signup(req.email, req.password, req.display_name)
        except ServiceError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return TokenResponse(token=service_login(service, req.email, req.password))

    @app.post("/auth/login", response_model=TokenResponse)
    def login(req: LoginRequest):
        _throttle_control(control_limiter, f"login:{req.email.lower()}")
        try:
            token = service.login(req.email, req.password)
        except ServiceError:
            raise HTTPException(status_code=401, detail="invalid_credentials")
        return TokenResponse(token=token)

    @app.get("/auth/me")
    def me(user=Depends(current_user)):
        return {"user_id": user.user_id, "email": user.email, "display_name": user.display_name}

    # ---------------- projects ----------------
    @app.post("/projects")
    def create_project(req: CreateProjectRequest, user=Depends(current_user)):
        try:
            p = service.create_project(user.user_id, req.name, req.environment)
        except ServiceError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"project_id": p.project_id, "name": p.name, "environment": p.environment}

    @app.get("/projects")
    def list_projects(user=Depends(current_user)):
        return {"projects": [
            {"project_id": p.project_id, "name": p.name, "environment": p.environment,
             "created_at": p.created_at}
            for p in service.list_projects(user.user_id)
        ]}

    # ---------------- models ----------------
    @app.post("/models")
    def register_model(req: RegisterModelRequest, user=Depends(current_user)):
        try:
            m = service.register_model(user.user_id, req.project_id, req.name)
        except ServiceError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"model_id": m.model_id, "project_id": m.project_id, "name": m.name}

    @app.get("/models")
    def list_models(project_id: str | None = None, user=Depends(current_user)):
        try:
            models = service.list_models(user.user_id, project_id)
        except ServiceError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"models": [
            {"model_id": m.model_id, "project_id": m.project_id, "name": m.name,
             "status": m.status, "created_at": m.created_at}
            for m in models
        ]}

    # ---------------- API keys ----------------
    @app.post("/keys")
    def create_key(req: CreateKeyRequest, user=Depends(current_user)):
        # Throttle key minting per user (anti key-farming). Requires a valid
        # bearer token already, so this is a modest per-account cap.
        _throttle_control(control_limiter, f"keygen:{user.user_id}")
        try:
            raw, meta = service.create_api_key(
                user.user_id, req.project_id, req.model_id, req.name, req.expires_at
            )
        except ServiceError as e:
            raise HTTPException(status_code=404, detail=str(e))
        # Raw key returned exactly once.
        return {"api_key": raw, **meta}

    @app.get("/keys")
    def list_keys(user=Depends(current_user)):
        return {"api_keys": service.list_api_keys(user.user_id)}

    @app.delete("/keys/{key_id}")
    def revoke_key(key_id: str, user=Depends(current_user)):
        ok = service.revoke_api_key(user.user_id, key_id)
        if not ok:
            raise HTTPException(status_code=404, detail="key_not_found")
        return {"status": "revoked", "key_id": key_id}

    # ---------------- upstream config (existing-ML-API protection) ----------------
    @app.put("/models/{model_id}/upstream")
    def set_upstream(model_id: str, req: UpstreamRequest, user=Depends(current_user)):
        try:
            service.set_upstream(
                user.user_id, model_id, url=req.url, method=req.method,
                predict_path=req.predict_path, request_format=req.request_format,
                response_format=req.response_format, auth_type=req.auth_type,
                auth_secret=req.auth_secret, auth_header_name=req.auth_header_name,
                timeout_s=req.timeout_s,
            )
        except ServiceError as e:
            # A rejected/unsafe upstream URL is a client error (400); a
            # not-owned model is 404.
            msg = str(e)
            code = 400 if msg.startswith("upstream_url_") else 404
            raise HTTPException(status_code=code, detail=msg)
        except RuntimeError as e:
            # Encryption unavailable while an upstream secret was supplied.
            raise HTTPException(status_code=503, detail=str(e))
        # Never echo the secret back.
        return {"status": "configured", "model_id": model_id, "url": req.url,
                "auth_type": req.auth_type}

    # ---------------- tenant-scoped monitoring ----------------
    @app.get("/v1/threats")
    def threats(limit: int = 100, user=Depends(current_user)):
        pids = service.project_ids_for_user(user.user_id)
        return {"threats": store._telemetry.get_threats(limit=limit, project_ids=pids)}

    @app.get("/v1/threats/{request_id}")
    def threat_detail(request_id: str, user=Depends(current_user)):
        event = store.get_telemetry(request_id)
        if not event:
            raise HTTPException(status_code=404, detail="not_found")
        # Tenant check: the row's project must belong to the user.
        if event.get("project_id") not in set(service.project_ids_for_user(user.user_id)):
            raise HTTPException(status_code=404, detail="not_found")
        event["feedback"] = store.get_feedback(request_id)
        return event

    @app.get("/v1/metrics")
    def metrics(user=Depends(current_user)):
        pids = service.project_ids_for_user(user.user_id)
        return store._telemetry.metrics_summary(project_ids=pids)

    # ---------------- data plane ----------------
    @app.get("/v1/health")
    def health():
        return {
            "status": "ok",
            "mode": engine.mode,
            "detector_ready": engine.anomaly_detector.ready,
            "llm_provider": engine.investigation_agent.llm.name,
        }

    # MVP request-size bounds for the data plane (defence against resource
    # exhaustion). Configurable via env; generous enough for normal batch
    # inference but not unbounded.
    max_rows = int(os.getenv("BATMAN_MAX_PREDICT_ROWS", "1000"))
    max_cols = int(os.getenv("BATMAN_MAX_PREDICT_COLS", "4096"))

    # Per-model upstream-adapter cache. Rebuilding an HTTPModelAdapter per
    # request opens a fresh TCP connection each time (hundreds of ms on some
    # platforms). We cache one adapter per (model_id, config-version) so the
    # httpx connection pool is reused; a changed upstream config (new
    # updated_at) transparently supersedes the cached adapter.
    import threading

    _adapter_cache: dict[str, tuple[str, Any]] = {}
    _adapter_lock = threading.Lock()

    def _get_adapter(cfg):
        version = getattr(cfg, "updated_at", "") or ""
        with _adapter_lock:
            cached = _adapter_cache.get(cfg.model_id)
            if cached and cached[0] == version:
                return cached[1]
            # Config is new or changed: build a fresh adapter, retire the old.
            if cached:
                try:
                    cached[1].close()
                except Exception:
                    pass
            adapter = adapter_from_config(cfg)
            _adapter_cache[cfg.model_id] = (version, adapter)
            return adapter

    @app.post("/v1/predict")
    def predict(req: PredictRequest, key=Depends(authenticate_api_key)):
        # 0) Bound the request size before any processing.
        _validate_predict_size(req.inputs, max_rows, max_cols)

        # 1) Detection + policy + telemetry (NO model call yet).
        decision, _out, event = engine.analyze_request(
            req.inputs,
            project_id=key.project_id,
            model_id=key.model_id,
            session_id=req.session_id,
            key_id=key.key_id,
            run_model=False,
        )

        if decision.action == Action.BLOCK and engine.mode == "enforce":
            raise HTTPException(status_code=403, detail={"message": "blocked", **decision.to_dict()})

        # 2) Only if allowed (and not analyze-only) do we call the upstream model.
        prediction = None
        if not req.analyze_only and decision.allowed():
            cfg = service.get_upstream(key.model_id)
            if cfg is not None:
                # Reuse a pooled adapter (see _get_adapter) instead of building
                # a new HTTP connection per request.
                adapter = _get_adapter(cfg)
                try:
                    prediction = adapter.predict(req.inputs)
                except MLServiceError:
                    raise HTTPException(status_code=502, detail={"message": "upstream_error"})

        body = decision.to_dict()
        body["request_id"] = event.request_id
        body["latency_ms"] = event.latency_ms
        body["prediction"] = prediction
        if decision.action == Action.RATE_LIMIT and engine.mode == "enforce":
            body["note"] = "rate_limited"
        return body

    # ---------------- analyst feedback (dashboard, Bearer, tenant-scoped) ----------------
    @app.post("/v1/feedback")
    def submit_feedback(req: FeedbackRequest, user=Depends(current_user)):
        try:
            service.submit_feedback(
                user.user_id, req.request_id, req.label, req.analyst_note
            )
        except ServiceError as e:
            code = 400 if str(e) == "invalid_label" else 404
            raise HTTPException(status_code=code, detail=str(e))
        return {"status": "recorded", "request_id": req.request_id}

    @app.get("/v1/feedback")
    def list_feedback(limit: int = 200, user=Depends(current_user)):
        return {"feedback": service.list_feedback(user.user_id, limit=limit)}

    # ---------------- data-plane feedback (SDK / API-key auth) ----------------
    @app.post("/v1/data/feedback")
    def data_feedback(
        request_id: str, label: str, analyst_note: str = "", key=Depends(authenticate_api_key)
    ):
        if label not in VALID_FEEDBACK_LABELS:
            raise HTTPException(status_code=400, detail="invalid_label")
        event = store.get_telemetry(request_id)
        if not event or event.get("project_id") != key.project_id:
            raise HTTPException(status_code=404, detail="not_found")
        store.record_feedback(FeedbackRecord(request_id=request_id, label=label, analyst_note=analyst_note))
        return {"status": "recorded", "request_id": request_id}

    return app


def _throttle_control(limiter: SlidingWindowRateLimiter, key: str) -> None:
    if not limiter.check(key).allowed:
        raise HTTPException(status_code=429, detail="too_many_requests")


def _validate_predict_size(inputs: Any, max_rows: int, max_cols: int) -> None:
    """Reject oversized prediction payloads (MVP resource-exhaustion guard).

    Accepts a 2D-style structure (list of rows). We only bound the outer row
    count and, when rows look like sequences, the per-row length. Non-list
    inputs are passed through unchanged for the engine to validate.
    """
    if not isinstance(inputs, (list, tuple)):
        return
    if len(inputs) > max_rows:
        raise HTTPException(status_code=413, detail="request_too_large_rows")
    for row in inputs:
        if isinstance(row, (list, tuple)) and len(row) > max_cols:
            raise HTTPException(status_code=413, detail="request_too_large_cols")


def service_login(service: ControlPlaneService, email: str, password: str) -> str:
    """Issue a token right after signup without re-raising service errors."""
    return service.login(email, password)


# Default app instance (uses BATMAN_DATABASE_URL or sqlite default).
app = create_cloud_app(enable_llm=os.getenv("BATMAN_LLM_PROVIDER", "stub") != "stub")
