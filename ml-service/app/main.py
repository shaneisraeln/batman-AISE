"""Real ML inference service (FastAPI).

This is the *protected model* — a genuine classifier served over HTTP,
independent of BATMAN. BATMAN proxies to this service exactly as it would to any
third-party ML API.

Endpoints:
    GET  /health
    GET  /info
    POST /predict
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app import __version__
from app.model import Model
from app.preprocessing import feature_contract
from app.schemas import HealthResponse, PredictRequest, PredictResponse

app = FastAPI(title="ML Inference Service (Breast Cancer Diagnostic)", version=__version__)

_model: Model | None = None
# Observability counter: how many times /predict actually executed inference.
# Used in Step 3 to PROVE that blocked/rate-limited requests never reach the model.
_predict_calls = 0


def get_model() -> Model:
    global _model
    if _model is None:
        _model = Model()
    return _model


@app.get("/health", response_model=HealthResponse)
def health():
    try:
        m = get_model()
        return HealthResponse(status="ok", model_loaded=True, n_features=m.n_features)
    except Exception:
        return HealthResponse(status="degraded", model_loaded=False, n_features=0)


@app.get("/info")
def info():
    m = get_model()
    return {
        "service": "ml-inference",
        "version": __version__,
        "model": m.metadata.get("model_type"),
        "dataset": m.metadata.get("dataset"),
        "test_metrics": m.metadata.get("test_metrics"),
        **feature_contract(),
    }


@app.get("/stats")
def stats():
    """How many inference calls actually executed. For integration verification."""
    return {"predict_calls": _predict_calls}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    global _predict_calls
    try:
        m = get_model()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        out = m.predict(req.instances)
        _predict_calls += 1
    except Exception:
        # Controlled error — never leak internal exceptions.
        raise HTTPException(status_code=500, detail="inference_error")
    return PredictResponse(
        predictions=out["predictions"],
        labels=out["labels"],
        probabilities=out["probabilities"],
        model_version=__version__,
    )
