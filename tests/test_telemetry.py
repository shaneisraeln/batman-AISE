from batman.feedback.service import FeedbackService
from batman.telemetry.schema import TelemetryEvent, new_request_id, utcnow_iso
from batman.telemetry.store import TelemetryStore
import pytest


def _event(threat="MODEL_EXTRACTION", action="BLOCK"):
    return TelemetryEvent(
        request_id=new_request_id(),
        timestamp=utcnow_iso(),
        project_id="p",
        model_id="m",
        session_id="s",
        detector_version="1.0",
        features={"request_rate": 100.0},
        anomaly_score=0.8,
        extraction_score=0.9,
        threat_type=threat,
        threat_level="HIGH",
        action=action,
        latency_ms=12.0,
    )


def test_record_and_query_threats(tmp_db):
    store = TelemetryStore(tmp_db)
    ev = _event()
    store.record_telemetry(ev)
    threats = store.get_threats()
    assert len(threats) == 1
    assert threats[0]["threat_type"] == "MODEL_EXTRACTION"
    # NONE threats are excluded from get_threats.
    store.record_telemetry(_event(threat="NONE", action="ALLOW"))
    assert len(store.get_threats()) == 1
    store.close()


def test_metrics_summary(tmp_db):
    store = TelemetryStore(tmp_db)
    store.record_telemetry(_event(action="BLOCK"))
    store.record_telemetry(_event(threat="NONE", action="ALLOW"))
    m = store.metrics_summary()
    assert m["total_requests"] == 2
    assert m["blocked"] == 1
    assert m["allowed"] == 1
    store.close()


def test_feedback_separate_from_telemetry(tmp_db):
    store = TelemetryStore(tmp_db)
    ev = _event()
    store.record_telemetry(ev)
    svc = FeedbackService(store)
    svc.submit(ev.request_id, "FALSE_POSITIVE", "batch job")
    fb = svc.for_request(ev.request_id)
    assert len(fb) == 1
    assert fb[0]["label"] == "FALSE_POSITIVE"
    store.close()


def test_invalid_feedback_label_rejected(tmp_db):
    store = TelemetryStore(tmp_db)
    svc = FeedbackService(store)
    with pytest.raises(ValueError):
        svc.submit("req_1", "NOT_A_LABEL")
    store.close()
