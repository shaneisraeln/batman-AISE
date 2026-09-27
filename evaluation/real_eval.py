"""Step 6 — Rigorous detector validation against the REAL-service distribution.

This evaluates BATMAN's detection layer using the SAME feature pipeline,
detector artifact, and thresholds the live gateway uses (breast-cancer
calibrated). It is an OFFLINE replay: it reuses the runtime FeatureExtractor,
SessionStore, rules, IsolationForest, and extraction detector directly, so the
numbers correspond to what the live gateway would decide.

Provenance is explicit and separated:
  - SYNTHETIC attack generation (labels): controlled traffic from attacks/*.
  - REAL feature pipeline + detector: batman.* runtime components.
  - Live-path telemetry from Steps 4/5 is reported separately (SQLite),
    not conflated with this offline detector benchmark.

Outputs (per ablation + generalization):
  confusion matrix, precision, recall, F1, TPR, FPR, TNR, classification
  accuracy (explicitly NOT F1), per-attack-class recall, latency p50/p95/p99.

Ablation:
  A  rules only
  B  isolation forest only
  C  isolation forest + extraction detector
  D  full BATMAN hybrid (rules OR IF OR extraction)

Run:  python -m evaluation.real_eval
"""

from __future__ import annotations

import json
import time

import numpy as np

from attacks.abuse import generate_abuse
from attacks.anomalies import generate_anomalies
from attacks.extraction import generate_extraction
from attacks.normal import generate_normal
from batman.detection.extraction import ExtractionDetector
from batman.detection.isolation_forest import IsolationForestDetector
from batman.detection.rules import RulesEngine
from batman.features.extractor import FeatureExtractor
from batman.features.session import SessionStore
from evaluation.metrics import compute_metrics
from training.prepare import load_reference

DETECTOR_PATH = "models/isolation_forest_breast_cancer.joblib"
EXTRACTION_THRESHOLD = 0.6


def _build_labeled_events(reference, seed=100, extraction_strategy="A"):
    """Controlled, labeled traffic against the real-service feature space.

    Ground-truth class per event: NORMAL / ABUSE / EXTRACTION / ANOMALY.
    """
    events = []
    events += generate_normal(reference, n_sessions=40, seed=seed)
    events += generate_abuse(reference, n_sessions=8, seed=seed + 1)
    events += generate_extraction(
        reference, strategy=extraction_strategy, n_sessions=6, seed=seed + 2
    )
    events += generate_anomalies(reference, n_sessions=8, seed=seed + 3)
    return events


def _replay_with_state(events, detector, extraction_detector, rules, capture_latency=False):
    """Replay events through the real pipeline, keeping per-session state so the
    extraction detector sees accumulating context (as it does at runtime).

    Returns per-event dicts: label, rule_flag, if_flag, ext_score, latency_ms.
    """
    extractor = FeatureExtractor()
    sessions = SessionStore()
    clock: dict[str, float] = {}
    out = []

    for ev in events:
        now = clock.get(ev.session_id, 0.0) + ev.dt
        clock[ev.session_id] = now
        arr = np.asarray(ev.inputs, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        session = sessions.get(ev.session_id)
        session.record(ts=now, input_vec=arr[0])

        t0 = time.perf_counter()
        feats = extractor.extract(arr, session, now=now)
        fd = feats.to_dict()
        rule_events = rules.evaluate(fd)
        det = detector.predict(feats.vector())
        ext = extraction_detector.detect(fd, session)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        session.anomaly_history.append(det.score)

        rule_flag = any(r.severity in ("high", "medium") for r in rule_events)
        out.append(
            {
                "label": ev.label,
                "rule_flag": rule_flag,
                "if_flag": det.is_anomalous,
                "ext_score": ext.score,
                "latency_ms": latency_ms,
            }
        )
    return out


def _is_suspicious(label: str) -> bool:
    return label != "NORMAL"


def _ablation(rows, exclude_labels=None):
    """Ablation over the given rows. `exclude_labels` drops classes owned by a
    different enforcement layer (e.g. ABUSE, owned by the rate limiter) so the
    behavioral detector is judged on the threats it is actually responsible for.
    """
    exclude = set(exclude_labels or [])
    rows = [r for r in rows if r["label"] not in exclude]
    truth = [_is_suspicious(r["label"]) for r in rows]
    pred_a = [r["rule_flag"] for r in rows]
    pred_b = [r["if_flag"] for r in rows]
    pred_c = [r["if_flag"] or r["ext_score"] >= EXTRACTION_THRESHOLD for r in rows]
    pred_d = [
        r["rule_flag"] or r["if_flag"] or r["ext_score"] >= EXTRACTION_THRESHOLD
        for r in rows
    ]
    return {
        "A_rules_only": compute_metrics(truth, pred_a).to_dict(),
        "B_isolation_forest_only": compute_metrics(truth, pred_b).to_dict(),
        "C_if_plus_extraction": compute_metrics(truth, pred_c).to_dict(),
        "D_full_batman_hybrid": compute_metrics(truth, pred_d).to_dict(),
    }


def _per_class_recall(rows):
    """Recall of the full hybrid detector broken down by attack class."""
    classes = {}
    for r in rows:
        if r["label"] == "NORMAL":
            continue
        flagged = (
            r["rule_flag"] or r["if_flag"] or r["ext_score"] >= EXTRACTION_THRESHOLD
        )
        c = classes.setdefault(r["label"], {"total": 0, "detected": 0})
        c["total"] += 1
        c["detected"] += 1 if flagged else 0
    return {
        k: {
            "total": v["total"],
            "detected": v["detected"],
            "recall": round(v["detected"] / v["total"], 4) if v["total"] else 0.0,
        }
        for k, v in classes.items()
    }


def _latency_percentiles(rows):
    lat = sorted(r["latency_ms"] for r in rows)
    if not lat:
        return {}

    def pct(p):
        idx = min(len(lat) - 1, int(round((p / 100.0) * (len(lat) - 1))))
        return round(lat[idx], 4)

    return {
        "samples": len(lat),
        "p50_ms": pct(50),
        "p95_ms": pct(95),
        "p99_ms": pct(99),
        "mean_ms": round(float(np.mean(lat)), 4),
        "max_ms": round(lat[-1], 4),
    }


def run() -> dict:
    reference = load_reference("breast_cancer")
    detector = IsolationForestDetector.load(DETECTOR_PATH)
    if not detector.ready:
        raise RuntimeError(
            "breast-cancer detector missing. Run: "
            "python -m training.prepare && python -m training.train --dataset breast_cancer"
        )
    extraction_detector = ExtractionDetector()
    rules = RulesEngine()

    # Main evaluation (extraction strategy A).
    events_a = _build_labeled_events(reference, seed=100, extraction_strategy="A")
    rows_a = _replay_with_state(events_a, detector, extraction_detector, rules)

    # Generalization: detector/threshold unchanged (calibrated on normal only),
    # evaluate against an UNSEEN extraction strategy B.
    events_b = generate_normal(reference, n_sessions=25, seed=300)
    events_b += generate_extraction(reference, strategy="B", n_sessions=6, seed=301)
    rows_b = _replay_with_state(events_b, detector, extraction_detector, rules)
    truth_b = [_is_suspicious(r["label"]) for r in rows_b]
    pred_b = [
        r["rule_flag"] or r["if_flag"] or r["ext_score"] >= EXTRACTION_THRESHOLD
        for r in rows_b
    ]

    return {
        "provenance": {
            "attack_traffic": "SYNTHETIC / CONTROLLED (attacks/* generators)",
            "feature_pipeline_and_detector": "REAL runtime components (batman.*), "
            "breast-cancer calibrated",
            "note": "Offline replay of the real pipeline. Live-path telemetry from "
            "Steps 4-5 is reported separately in SQLite, not merged here.",
        },
        "dataset": {
            "distribution": "Breast Cancer Wisconsin feature space (30-dim)",
            "n_events_main": len(rows_a),
            "class_counts": _class_counts(rows_a),
        },
        "ablation_all_classes_strategy_A": _ablation(rows_a),
        "ablation_detector_scope_strategy_A": {
            "scope_note": "Excludes ABUSE, which is a rate/frequency attack owned "
            "by the deterministic rate limiter (see Step 5 live results), not the "
            "content-based behavioral detector. This isolates the detector's own "
            "responsibility: EXTRACTION + ANOMALY vs NORMAL.",
            **_ablation(rows_a, exclude_labels=["ABUSE"]),
        },
        "per_class_recall_full_hybrid": _per_class_recall(rows_a),
        "latency": _latency_percentiles(rows_a),
        "generalization_A_to_B": {
            "calibrated_on": "NORMAL behavior only (unsupervised); main eval used extraction A",
            "tested_on": "NORMAL + extraction strategy B (unseen)",
            "metrics": compute_metrics(truth_b, pred_b).to_dict(),
        },
    }


def _class_counts(rows):
    counts = {}
    for r in rows:
        counts[r["label"]] = counts.get(r["label"], 0) + 1
    return counts


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--json", default=None)
    args = p.parse_args()
    results = run()
    print(json.dumps(results, indent=2))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nwrote {args.json}")
