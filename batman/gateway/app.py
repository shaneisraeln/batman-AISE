"""FastAPI gateway.

Endpoints:
    POST /v1/predict
    POST /v1/feedback
    GET  /v1/threats
    GET  /v1/threats/{request_id}
    GET  /v1/metrics
    GET  /v1/health
    POST /v1/keys           (admin helper to mint keys for the demo)

The gateway shares the same SecurityEngine as the SDK.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from batman.config import get_settings
from batman.engine import SecurityEngine
from batman.gateway.auth import APIKeyStore, AuthError
from batman.telemetry.schema import VALID_FEEDBACK_LABELS, FeedbackRecord
from batman.telemetry.store import TelemetryStore
from batman.types import Action


# --- request/response models ---
class PredictRequest(BaseModel):
    inputs: Any = Field(..., description="Numeric array (1D or 2D) of model inputs")
    session_id: str = Field("default", description="Client/session identifier")


class FeedbackRequest(BaseModel):
    request_id: str
    label: str
    analyst_note: str = ""


class CreateKeyRequest(BaseModel):
    project_id: str = "demo-project"
    model_id: str = "demo-model"
    expires_at: str | None = None


def create_app(model: object | None = None, enable_llm: bool = True) -> FastAPI:
    import os

    settings = get_settings()
    store = TelemetryStore(settings.db_path)
    # Allow the detector artifact to be selected per protected service, so the
    # behavioral detector is calibrated for the distribution it actually guards.
    detector_path = os.getenv("BATMAN_DETECTOR_PATH", "models/isolation_forest.joblib")
    engine = SecurityEngine(
        model=model,
        settings=settings,
        store=store,
        enable_llm=enable_llm,
        detector_path=detector_path,
    )
    key_store = APIKeyStore(store)

    app = FastAPI(title="BATMAN Gateway", version="2.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.engine = engine
    app.state.store = store
    app.state.key_store = key_store

    def authenticate(x_api_key: str | None = Header(default=None)) -> dict:
        """Authenticate the request. Returns project/model context.

        For the demo we allow unauthenticated calls to fall back to a default
        project so the dashboard works out of the box, but a provided key is
        always verified.
        """
        if x_api_key:
            try:
                record = key_store.authenticate(x_api_key)
                return {
                    "project_id": record.project_id,
                    "model_id": record.model_id,
                    "key_id": record.key_id,
                    "auth_error": None,
                }
            except AuthError as exc:
                # Record the auth failure as a security event, but signal 401.
                raise HTTPException(status_code=401, detail=str(exc))
        return {
            "project_id": "default",
            "model_id": "default",
            "key_id": None,
            "auth_error": None,
        }

    @app.get("/v1/health")
    def health() -> dict:
        return {
            "status": "ok",
            "mode": engine.mode,
            "detector_ready": engine.anomaly_detector.ready,
            "llm_provider": engine.investigation_agent.llm.name,
            "rag_backend": getattr(
                getattr(engine.investigation_agent, "retriever", None), "backend", "none"
            ),
        }

    @app.post("/v1/predict")
    def predict(req: PredictRequest, ctx: dict = Depends(authenticate)) -> dict:
        decision, output, event = engine.analyze_request(
            req.inputs,
            project_id=ctx["project_id"],
            model_id=ctx["model_id"],
            session_id=req.session_id,
            key_id=ctx["key_id"],
            auth_error=ctx["auth_error"],
            run_model=True,
        )
        if decision.action == Action.RATE_LIMIT and engine.mode == "enforce":
            # Surface a 429 but still return the decision body.
            return _resp(decision, output, event, http_note="rate_limited")
        if decision.action == Action.BLOCK and engine.mode == "enforce":
            raise HTTPException(
                status_code=403,
                detail={"message": "blocked", **decision.to_dict()},
            )
        return _resp(decision, output, event)

    @app.post("/v1/feedback")
    def feedback(req: FeedbackRequest) -> dict:
        if req.label not in VALID_FEEDBACK_LABELS:
            raise HTTPException(status_code=400, detail="invalid_label")
        store.record_feedback(
            FeedbackRecord(
                request_id=req.request_id,
                label=req.label,
                analyst_note=req.analyst_note,
            )
        )
        return {"status": "recorded", "request_id": req.request_id}

    @app.get("/v1/threats")
    def threats(limit: int = 100) -> dict:
        return {"threats": store.get_threats(limit=limit)}

    @app.get("/v1/threats/{request_id}")
    def threat_detail(request_id: str) -> dict:
        event = store.get_telemetry(request_id)
        if not event:
            raise HTTPException(status_code=404, detail="not_found")
        event["feedback"] = store.get_feedback(request_id)
        return event

    @app.get("/v1/metrics")
    def metrics() -> dict:
        return store.metrics_summary()

    @app.post("/v1/keys")
    def create_key(req: CreateKeyRequest) -> dict:
        raw, record = key_store.create_key(
            project_id=req.project_id,
            model_id=req.model_id,
            expires_at=req.expires_at,
        )
        # Raw key returned once, never logged or persisted.
        return {"api_key": raw, "key_id": record.key_id, "project_id": record.project_id}

    return app


def _resp(decision, output, event, http_note: str | None = None) -> dict:
    body = decision.to_dict()
    body["request_id"] = event.request_id
    body["latency_ms"] = event.latency_ms
    body["prediction"] = _jsonable(output)
    if http_note:
        body["note"] = http_note
    return body


def _jsonable(x):
    try:
        import numpy as np

        if isinstance(x, np.ndarray):
            return x.tolist()
    except Exception:
        pass
    return x


# Default app instance selects a protected model in this priority:
#   1. BATMAN_PROTECTED_MODEL_URL set -> proxy to a real external ML API (Phase 1).
#   2. otherwise -> load the local demo joblib model in-process (legacy behavior).
def _default_model():
    import os

    url = os.getenv("BATMAN_PROTECTED_MODEL_URL")
    if url:
        from batman.adapters_http import HTTPModelAdapter

        return HTTPModelAdapter(
            base_url=url,
            predict_path=os.getenv("BATMAN_PROTECTED_MODEL_PATH", "/predict"),
        )
    try:
        import joblib

        path = os.path.join("models", "demo_model.joblib")
        if os.path.exists(path):
            return joblib.load(path)
    except Exception:
        pass
    return None


app = create_app(model=_default_model())
