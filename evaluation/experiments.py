"""Baseline experiments and the flagship generalization test.

Baselines:
  A  Rules only
  B  Isolation Forest anomaly detector only
  C  BATMAN = Rules + behavioral ML + extraction signals (full pipeline)

Also runs the generalization experiment (train on extraction strategy A, test
on strategy B) and a latency benchmark of the deterministic + detector path.

Run: python -m evaluation.experiments
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
from batman.features.behavioral import FEATURE_ORDER
from batman.features.extractor import FeatureExtractor
from batman.features.session import SessionStore
from evaluation.drift import compute_psi
from evaluation.metrics import compute_metrics
from training.prepare import load_reference
from training.replay import replay_events

DETECTOR_PATH = "models/isolation_forest.joblib"


def _build_eval_events(reference, extraction_strategy: str = "A", seed: int = 100):
    events = []
    events += generate_normal(reference, n_sessions=30, seed=seed)
    events += generate_abuse(reference, n_sessions=8, seed=seed + 1)
    events += generate_extraction(
        reference, strategy=extraction_strategy, n_sessions=6, seed=seed + 2
    )
    events += generate_anomalies(reference, n_sessions=6, seed=seed + 3)
    return events


def _is_suspicious(label: str) -> bool:
    return label != "NORMAL"


def _run_baselines(reference, detector, extraction_strategy="A"):
    events = _build_eval_events(reference, extraction_strategy)
    X, labels, feat_dicts = replay_events(events)
    truth = [_is_suspicious(l) for l in labels]

    rules = RulesEngine()
    extraction_detector = ExtractionDetector()
    sessions = SessionStore()  # fresh sessions for extraction detector context

    pred_a, pred_b, pred_c = [], [], []
    for i, (row, fd) in enumerate(zip(X, feat_dicts)):
        # A: rules only.
        rule_events = rules.evaluate(fd)
        flagged_a = any(r.severity in ("high", "medium") for r in rule_events)
        pred_a.append(flagged_a)

        # B: isolation forest only.
        det = detector.predict(row)
        pred_b.append(det.is_anomalous)

        # C: full hybrid — rules OR anomaly OR extraction.
        session = sessions.get(f"eval_{i}")
        ext = extraction_detector.detect(fd, session)
        flagged_c = flagged_a or det.is_anomalous or ext.score >= 0.6
        pred_c.append(flagged_c)

    return {
        "A_rules_only": compute_metrics(truth, pred_a).to_dict(),
        "B_isolation_forest": compute_metrics(truth, pred_b).to_dict(),
        "C_batman_hybrid": compute_metrics(truth, pred_c).to_dict(),
        "n_events": len(labels),
    }


def _generalization(reference, detector):
    """Train context on strategy A, evaluate detection on strategy B extraction."""
    # We reuse the same trained detector; the test is whether behavioral signals
    # generalize to an unseen extraction strategy.
    events = generate_normal(reference, n_sessions=20, seed=300)
    events += generate_extraction(reference, strategy="B", n_sessions=6, seed=301)
    X, labels, feat_dicts = replay_events(events)
    truth = [_is_suspicious(l) for l in labels]

    extraction_detector = ExtractionDetector()
    sessions = SessionStore()
    preds = []
    for i, (row, fd) in enumerate(zip(X, feat_dicts)):
        det = detector.predict(row)
        session = sessions.get(f"gen_{i}")
        ext = extraction_detector.detect(fd, session)
        preds.append(det.is_anomalous or ext.score >= 0.6)
    return {
        "trained_on": "extraction_strategy_A + normal",
        "tested_on": "extraction_strategy_B + normal",
        "metrics": compute_metrics(truth, preds).to_dict(),
    }


def _latency_benchmark(reference, detector, n: int = 300):
    """Measure deterministic + detector path latency (excludes LLM/RAG)."""
    extractor = FeatureExtractor()
    extraction_detector = ExtractionDetector()
    rules = RulesEngine()
    sessions = SessionStore()
    ref = np.asarray(reference, dtype=float)
    rng = np.random.default_rng(7)

    latencies = []
    for i in range(n):
        x = ref[int(rng.integers(0, ref.shape[0]))].reshape(1, -1)
        session = sessions.get("bench")
        t0 = time.perf_counter()
        session.record(ts=float(i), input_vec=x[0])
        feats = extractor.extract(x, session, now=float(i))
        fd = feats.to_dict()
        rules.evaluate(fd)
        detector.predict(feats.vector())
        extraction_detector.detect(fd, session)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    latencies.sort()
    return {
        "samples": n,
        "mean_ms": round(float(np.mean(latencies)), 4),
        "p50_ms": round(latencies[len(latencies) // 2], 4),
        "p95_ms": round(latencies[int(len(latencies) * 0.95)], 4),
        "max_ms": round(latencies[-1], 4),
    }


def _drift_check(reference, detector):
    normal = generate_normal(reference, n_sessions=20, seed=500)
    drifted = generate_extraction(reference, strategy="A", n_sessions=6, seed=501)
    X_ref, _, _ = replay_events(normal)
    X_cur, _, _ = replay_events(drifted)
    return compute_psi(X_ref, X_cur, FEATURE_ORDER)


def run_all() -> dict:
    reference = load_reference()
    detector = IsolationForestDetector.load(DETECTOR_PATH)
    if not detector.ready:
        raise RuntimeError(
            "Detector not trained. Run: python -m training.prepare && python -m training.train"
        )

    results = {
        "baselines": _run_baselines(reference, detector),
        "generalization": _generalization(reference, detector),
        "latency": _latency_benchmark(reference, detector),
        "drift": _drift_check(reference, detector),
    }
    return results


if __name__ == "__main__":
    print(json.dumps(run_all(), indent=2))
