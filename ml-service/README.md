# ML Inference Service — Breast Cancer Diagnostic

A **real** ML inference service that BATMAN protects. It is intentionally
independent of BATMAN: BATMAN proxies to it over HTTP exactly as it would to any
third-party model API.

## Dataset

- **Breast Cancer Wisconsin (Diagnostic)** — bundled with scikit-learn.
- **Source:** UCI Machine Learning Repository (Wolberg, Street, Mangasarian).
- **Samples:** 569 · **Features:** 30 real-valued (cell-nucleus measurements:
  radius, texture, perimeter, area, smoothness, etc.) · **Target:** binary
  (`malignant` = 0, `benign` = 1).

## Preprocessing

- `StandardScaler` fit on the training split, saved inside the pipeline so
  inference applies the identical transform.

## Model

- `Pipeline(StandardScaler + LogisticRegression)`.
- **Split:** 60% train / 20% validation / 20% test, stratified, seed 42.
- Validation used for a sanity check; the test set is evaluated once.
- Held-out **test metrics** are written to `model/metadata.json` at training
  time (see `/info`). These are the real numbers, not placeholders.

## Inference format

```
POST /predict
{ "instances": [[f1, f2, ..., f30], ...] }

200 OK
{
  "predictions": [1],
  "labels": ["benign"],
  "probabilities": [[0.02, 0.98]],
  "model_version": "1.0.0"
}
```

Other endpoints: `GET /health`, `GET /info`.

## Run

```powershell
pip install -r requirements.txt
python -m app.train                 # writes model/model.joblib + metadata.json
uvicorn app.main:app --port 9000
```

Docker:

```powershell
docker build -t batman-ml-service .
docker run -p 9000:9000 batman-ml-service
```

## Limitations

- A diagnostic research dataset used as a stand-in for "a model worth
  protecting." It is **not** a clinical tool and must not be used for medical
  decisions.
- Single-process, in-memory model load; no batching optimizations. Adequate for
  BATMAN validation, not production ML serving.
