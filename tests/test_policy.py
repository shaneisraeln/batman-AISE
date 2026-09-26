from batman.policy.engine import PolicyConfig, PolicyEngine
from batman.types import Action, RuleEvent, ThreatEvidence, ThreatLevel


def test_high_severity_rule_blocks():
    pe = PolicyEngine(PolicyConfig(), mode="enforce")
    ev = ThreatEvidence(rule_events=[RuleEvent("nan_input", "high", "nan")])
    level, action, _ = pe.evaluate(ev)
    assert action == Action.BLOCK
    assert level == ThreatLevel.HIGH


def test_high_score_blocks():
    pe = PolicyEngine(PolicyConfig(), mode="enforce")
    ev = ThreatEvidence(extraction_score=0.9, confidence=0.8)
    _, action, _ = pe.evaluate(ev)
    assert action == Action.BLOCK


def test_medium_score_rate_limits():
    pe = PolicyEngine(PolicyConfig(), mode="enforce")
    ev = ThreatEvidence(anomaly_score=0.65, confidence=0.7)
    _, action, _ = pe.evaluate(ev)
    assert action == Action.RATE_LIMIT


def test_clean_request_allowed():
    pe = PolicyEngine(PolicyConfig(), mode="enforce")
    ev = ThreatEvidence(anomaly_score=0.1, extraction_score=0.0)
    _, action, _ = pe.evaluate(ev)
    assert action == Action.ALLOW


def test_monitor_mode_downgrades_blocking():
    pe = PolicyEngine(PolicyConfig(), mode="monitor")
    ev = ThreatEvidence(extraction_score=0.9, confidence=0.9)
    _, action, _ = pe.evaluate(ev)
    assert action == Action.LOG  # detect, don't block


def test_uncertain_escalates():
    pe = PolicyEngine(PolicyConfig(), mode="enforce")
    ev = ThreatEvidence(anomaly_score=0.6, confidence=0.1)
    level, action, _ = pe.evaluate(ev)
    assert action == Action.ESCALATE
    assert level == ThreatLevel.UNCERTAIN
