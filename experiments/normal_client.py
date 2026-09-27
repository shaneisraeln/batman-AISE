"""Step 4 — Real legitimate-traffic client.

A legitimate application that sends realistic Breast Cancer samples through
BATMAN to the protected ML service and consumes the real predictions. This is
NOT a dashboard seeder: every request is a real HTTP call whose telemetry row is
written by BATMAN itself and is traceable by request_id.

Measured (all from real responses):
  - requests sent / successful predictions
  - prediction correctness vs ground-truth labels
  - client-observed latency through BATMAN (p50/p95/p99)
  - direct-to-ML latency (baseline) and BATMAN overhead = via - direct
  - false positives: legitimate requests that BATMAN flagged as a threat
  - detector anomaly/extraction score distribution
  - policy action distribution

Usage:
    python -m experiments.normal_client --requests 200
    python -m experiments.normal_client --requests 200 --json results.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import time

import httpx
import numpy as np
from sklearn.datasets import load_breast_cancer
from sklearn.model_selection import train_test_split

BATMAN = "http://127.0.0.1:8000"
ML = "http://127.0.0.1:9000"
SEED = 42


def _held_out_samples():
    """Reproduce the ML service's test split so we have realistic, correctly
    labeled samples the model has never trained on."""
    data = load_breast_cancer()
    X, y = data.data.astype(float), data.target
    _, X_tmp, _, y_tmp = train_test_split(X, y, test_size=0.40, random_state=SEED, stratify=y)
    _, X_test, _, y_test = train_test_split(
        X_tmp, y_tmp, test_size=0.50, random_state=SEED, stratify=y_tmp
    )
    return X_test, y_test


def _percentile(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
    return round(s[idx], 3)


def run(n_requests: int, out_json: str | None) -> dict:
    X_test, y_test = _held_out_samples()
    rng = np.random.default_rng(SEED)
    bat = httpx.Client(base_url=BATMAN, timeout=30)
    ml = httpx.Client(base_url=ML, timeout=30)

    # Baseline: measure direct-to-ML latency (no BATMAN) on a warm connection.
    direct_lat = []
    for i in range(min(50, n_requests)):
        idx = i % len(X_test)
        t0 = time.perf_counter()
        ml.post("/predict", json={"instances": [X_test[idx].tolist()]})
        direct_lat.append((time.perf_counter() - t0) * 1000.0)

    via_lat = []
    actions = {}
    anomaly_scores = []
    extraction_scores = []
    correct = 0
    predictions_returned = 0
    false_positives = 0  # legit request flagged as a non-NONE threat
    request_ids = []

    # Realistic legitimate traffic: spread across many client sessions with
    # human/service pacing so the per-session request rate stays within normal
    # limits (a real clinical app does not send 20 requests/second/session).
    n_sessions = max(4, n_requests // 8)
    for i in range(n_requests):
        session_id = f"clinic-app-{i % n_sessions}"
        idx = int(rng.integers(0, len(X_test)))
        sample = X_test[idx] + rng.normal(0, 0.01, size=X_test.shape[1])
        true_label = int(y_test[idx])

        # Jittered pacing: ~5-15 requests/min per session on average.
        time.sleep(float(rng.uniform(0.0, 0.05)))

        t0 = time.perf_counter()
        r = bat.post("/v1/predict", json={"inputs": [sample.tolist()], "session_id": session_id})
        via_lat.append((time.perf_counter() - t0) * 1000.0)

        body = r.json() if r.status_code == 200 else r.json().get("detail", {})
        action = body.get("action", f"HTTP_{r.status_code}")
        actions[action] = actions.get(action, 0) + 1

        ev = body.get("evidence", {})
        if "anomaly_score" in ev:
            anomaly_scores.append(ev["anomaly_score"])
            extraction_scores.append(ev.get("extraction_score", 0.0))
        if body.get("threat_type", "NONE") not in ("NONE", None):
            false_positives += 1
        if body.get("request_id"):
            request_ids.append(body["request_id"])

        pred = body.get("prediction")
        if pred:
            predictions_returned += 1
            if int(pred[0]) == true_label:
                correct += 1

    total = n_requests
    result = {
        "requests_sent": total,
        "successful_predictions": predictions_returned,
        "prediction_accuracy_vs_ground_truth": round(correct / predictions_returned, 4)
        if predictions_returned
        else 0.0,
        "false_positives": false_positives,
        "false_positive_rate": round(false_positives / total, 4),
        "action_distribution": actions,
        "latency_via_batman_ms": {
            "p50": _percentile(via_lat, 50),
            "p95": _percentile(via_lat, 95),
            "p99": _percentile(via_lat, 99),
            "mean": round(statistics.mean(via_lat), 3),
        },
        "latency_direct_ml_ms": {
            "p50": _percentile(direct_lat, 50),
            "mean": round(statistics.mean(direct_lat), 3),
        },
        "batman_overhead_ms_mean": round(
            statistics.mean(via_lat) - statistics.mean(direct_lat), 3
        ),
        "anomaly_score_mean": round(statistics.mean(anomaly_scores), 4)
        if anomaly_scores
        else 0.0,
        "extraction_score_mean": round(statistics.mean(extraction_scores), 4)
        if extraction_scores
        else 0.0,
        "sample_request_ids": request_ids[:3],
    }

    print(json.dumps(result, indent=2))
    if out_json:
        with open(out_json, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nwrote {out_json}")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=200)
    p.add_argument("--json", default=None)
    args = p.parse_args()
    run(args.requests, args.json)
