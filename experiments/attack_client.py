"""Step 5 — Controlled security experiments against OUR OWN deployed service.

Every attack targets our own running BATMAN gateway (:8000), which proxies to
our own ML service (:9000). No third-party system is ever touched.

This is CONTROLLED, INTENTIONALLY GENERATED attack traffic used for a security
experiment. It is NOT naturally occurring production traffic and is labeled as
such wherever it surfaces (telemetry session ids are prefixed `CTRL-`).

Experiments:
  A  API abuse            — high-rate / bursty repeated requests
  B  Systematic probing   — steadily varied queries across a session
  C  Model extraction     — high-volume, high-diversity sweep of the input space
  D  Anomalous inputs     — out-of-range values / extreme norms (JSON-safe)

For each experiment we record, from REAL responses:
  requests sent, allowed, rate_limited, blocked, first-detection index,
  successful predictions before detection, mean detector scores, actions.

Usage:
    python -m experiments.attack_client --json experiments/results_attacks.json
"""

from __future__ import annotations

import argparse
import json
import time

import httpx
import numpy as np
from sklearn.datasets import load_breast_cancer

BATMAN = "http://127.0.0.1:8000"
SEED = 7


def _client():
    return httpx.Client(base_url=BATMAN, timeout=30)


def _feature_bounds():
    X = load_breast_cancer().data.astype(float)
    return X, X.min(axis=0), X.max(axis=0)


def _send(client, vec, session_id):
    """Send one request; return (action, threat_type, anomaly, extraction, reached_model)."""
    # JSON cannot carry NaN/Inf — map to large finite sentinels so BATMAN's
    # validation layer sees malformed-but-transmittable numbers (as a real
    # misbehaving client would send).
    arr = np.nan_to_num(np.asarray(vec, dtype=float), nan=1e12, posinf=1e12, neginf=-1e12)
    r = client.post("/v1/predict", json={"inputs": [arr.tolist()], "session_id": session_id})
    if r.status_code == 200:
        b = r.json()
    else:
        b = r.json().get("detail", {}) if r.headers.get("content-type", "").startswith("application/json") else {}
    ev = b.get("evidence", {})
    action = b.get("action", f"HTTP_{r.status_code}")
    return {
        "status": r.status_code,
        "action": action,
        "threat_type": b.get("threat_type", "NONE"),
        "anomaly": ev.get("anomaly_score", 0.0),
        "extraction": ev.get("extraction_score", 0.0),
        "reached_model": bool(b.get("prediction")),
        "request_id": b.get("request_id"),
    }


def _summarize(name, events, description):
    allowed = sum(1 for e in events if e["action"] in ("ALLOW", "LOG"))
    rate_limited = sum(1 for e in events if e["action"] == "RATE_LIMIT")
    blocked = sum(1 for e in events if e["action"] == "BLOCK" or e["status"] in (403, 429))
    reached = sum(1 for e in events if e["reached_model"])
    first_detect = next(
        (i for i, e in enumerate(events) if e["action"] not in ("ALLOW", "LOG")), None
    )
    succ_before = sum(1 for e in events[: first_detect if first_detect is not None else len(events)] if e["reached_model"])
    anomalies = [e["anomaly"] for e in events]
    extractions = [e["extraction"] for e in events]
    return {
        "experiment": name,
        "description": description,
        "requests_sent": len(events),
        "allowed": allowed,
        "rate_limited": rate_limited,
        "blocked": blocked,
        "reached_model_total": reached,
        "first_detection_index": first_detect,
        "successful_predictions_before_detection": succ_before,
        "mean_anomaly_score": round(float(np.mean(anomalies)), 4) if anomalies else 0.0,
        "mean_extraction_score": round(float(np.mean(extractions)), 4) if extractions else 0.0,
        "sample_request_ids": [e["request_id"] for e in events if e["request_id"]][:2],
    }


def experiment_a_abuse(client, X):
    """High-rate repeated requests from a single session (API abuse)."""
    rng = np.random.default_rng(SEED)
    base = X[int(rng.integers(0, len(X)))]
    events = []
    for _ in range(80):
        # Repeated identical payload hammered with no pacing.
        events.append(_send(client, base, "CTRL-abuse"))
    return _summarize("A_api_abuse", events, "high-rate repeated requests (no pacing)")


def experiment_b_probing(client, X, lo, hi):
    """Systematic probing: steadily varied queries within realistic bounds."""
    rng = np.random.default_rng(SEED + 1)
    events = []
    for i in range(80):
        # Interpolate across the feature space in an ordered sweep.
        t = i / 80.0
        vec = lo + (hi - lo) * (0.3 + 0.4 * t) + rng.normal(0, 0.5, size=X.shape[1])
        events.append(_send(client, vec, "CTRL-probing"))
        time.sleep(0.01)
    return _summarize("B_systematic_probing", events, "ordered systematic input variation")


def experiment_c_extraction(client, X, lo, hi):
    """Model extraction: high-volume, high-diversity sweep of the input space."""
    rng = np.random.default_rng(SEED + 2)
    events = []
    for _ in range(140):
        # Uniform coverage of the feature ranges = maximal query diversity.
        vec = lo + (hi - lo) * rng.random(X.shape[1])
        events.append(_send(client, vec, "CTRL-extraction"))
    return _summarize("C_model_extraction", events, "high-diversity input-space sweep")


def experiment_d_anomalous(client, X):
    """Anomalous inputs: out-of-range values and extreme norms."""
    rng = np.random.default_rng(SEED + 3)
    events = []
    for i in range(60):
        base = X[int(rng.integers(0, len(X)))].copy()
        kind = i % 3
        if kind == 0:
            vec = base * rng.uniform(10, 30)          # out-of-range scale-up
        elif kind == 1:
            vec = rng.normal(0, 500.0, size=X.shape[1])  # extreme norm
        else:
            vec = base.copy(); vec[int(rng.integers(0, len(vec)))] = 1e12  # spike
        events.append(_send(client, vec, "CTRL-anomalous"))
        time.sleep(0.01)
    return _summarize("D_anomalous_inputs", events, "out-of-range / extreme-norm inputs")


def run(out_json: str | None) -> dict:
    X, lo, hi = _feature_bounds()
    client = _client()
    results = {
        "note": "CONTROLLED SECURITY TEST — intentionally generated attack traffic "
        "against our own service. Not production traffic.",
        "experiments": [
            experiment_a_abuse(client, X),
            experiment_b_probing(client, X, lo, hi),
            experiment_c_extraction(client, X, lo, hi),
            experiment_d_anomalous(client, X),
        ],
    }
    print(json.dumps(results, indent=2))
    if out_json:
        with open(out_json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nwrote {out_json}")
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--json", default=None)
    args = p.parse_args()
    run(args.json)
