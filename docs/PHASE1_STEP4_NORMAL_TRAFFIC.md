# Phase 1 / Step 4 — Real Legitimate Traffic (measured)

**Client:** `experiments/normal_client.py` — a legitimate application sending
realistic Breast Cancer samples (held-out test split + tiny measurement noise)
through BATMAN to the real ML service, consuming real predictions. Every request
is a real HTTP call; telemetry is written by BATMAN and traceable by request_id.

## Results (200 requests, real path)

| Metric | Value |
|---|---|
| Requests sent | 200 |
| Successful predictions | 197 |
| Prediction accuracy vs ground truth | 94.9% |
| **False-positive rate (legit flagged)** | **1.5%** (3/200) |
| Action distribution | 174 ALLOW · 23 LOG · 3 RATE_LIMIT |
| Anomaly score mean (legit) | 0.207 (threshold 0.562) |
| Latency via BATMAN | p50 30.9 ms · p95 41.0 ms · p99 59.2 ms |
| Latency direct-to-ML (baseline) | p50 4.2 ms |
| **BATMAN overhead (mean)** | **~28 ms** end-to-end |

## Honest interpretation of the overhead

The ~28 ms is **end-to-end proxy overhead**, which includes an extra HTTP
round-trip BATMAN→ML service→BATMAN. The detector's own compute latency remains
~17 ms (measured in isolation); the additional ~11 ms is the network hop to the
external model. This is the real cost of running BATMAN as a gateway in front of
a separate service, and it is reported as such — not as isolated detector time.

## Real finding fixed during this step

The **first** run showed an **80% false-positive rate** on legitimate traffic.
Root cause (a genuine defect, not a test artifact):

> The behavioral detector was calibrated on the legacy **digits** reference
> pool (64-dim pixel vectors), but the real service consumes **30-dim Breast
> Cancer** features with a very different scale. Legitimate traffic looked
> anomalous.

**Fix (correct, not a workaround):** calibrate the detector on the *actual
protected service's* input distribution.
- `training/prepare.py::prepare_breast_cancer()` → `datasets/reference_breast_cancer.npz`
- `python -m training.train --dataset breast_cancer` → `models/isolation_forest_breast_cancer.joblib` (threshold 0.562)
- Gateway selects it via `BATMAN_DETECTOR_PATH`.

After recalibration, the legit false-positive rate dropped from **80% → 1.5%**.

A secondary first-run issue — the client hammering requests with no pacing,
which the rate limiter *correctly* throttled — was resolved by giving the client
realistic per-session pacing. This confirms the rate limiter behaves correctly;
it was the synthetic client that was unrealistic.

**Phase-1 lesson recorded:** a behavioral detector is only valid against the
distribution it was calibrated on. Per-service calibration is mandatory.

## Reproduce

```powershell
# calibrate detector for the real service (one time)
python -m training.prepare
python -m training.train --dataset breast_cancer

# run stack (ML :9000, gateway :8000 with the breast-cancer detector), then:
python -m experiments.normal_client --requests 200 --json experiments/results_normal.json
```
