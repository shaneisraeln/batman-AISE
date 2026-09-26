import numpy as np

from batman.detection.extraction import ExtractionDetector
from batman.detection.isolation_forest import (
    IsolationForestDetector,
    train_isolation_forest,
)
from batman.detection.rules import RulesEngine
from batman.features.behavioral import FEATURE_ORDER
from batman.features.session import SessionStore


def test_rules_flag_nan_and_rate():
    rules = RulesEngine(hard_rate_limit_rpm=100)
    events = rules.evaluate({"nan_count": 1, "request_rate": 150})
    names = {e.name for e in events}
    assert "nan_input" in names
    assert "hard_rate_limit" in names


def test_isolation_forest_train_and_score(reference):
    # Build synthetic normal feature rows.
    rng = np.random.default_rng(0)
    normal = rng.normal(0, 1, size=(200, len(FEATURE_ORDER)))
    artifacts = train_isolation_forest(normal, normal, target_fpr=0.05)
    det = IsolationForestDetector(artifacts)
    assert det.ready

    # A normal-ish point should score low; an extreme point should score high.
    normal_point = np.zeros(len(FEATURE_ORDER))
    extreme_point = np.full(len(FEATURE_ORDER), 50.0)
    s_norm = det.predict(normal_point).score
    s_ext = det.predict(extreme_point).score
    assert s_ext > s_norm


def test_unloaded_detector_is_safe():
    det = IsolationForestDetector(artifacts=None)
    res = det.predict(np.zeros(len(FEATURE_ORDER)))
    assert res.is_anomalous is False
    assert res.version == "unavailable"


def test_extraction_detector_flags_probing():
    ed = ExtractionDetector(rate_threshold=90)
    store = SessionStore()
    session = store.get("attacker")
    for i in range(40):
        session.recent_inputs.append(np.random.default_rng(i).normal(0, 1, 8))
    feats = {
        "request_rate": 120.0,
        "session_request_count": 120.0,
        "unique_input_ratio": 0.95,
        "duplicate_ratio": 0.05,
        "query_similarity": 0.7,
    }
    res = ed.detect(feats, session)
    assert res.score >= 0.6
    assert res.threat_type == "MODEL_EXTRACTION"
    assert len(res.evidence) >= 2
