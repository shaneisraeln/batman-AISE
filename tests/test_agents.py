from batman.agents.detection_agent import DetectionAgent
from batman.agents.investigation_agent import InvestigationAgent
from batman.agents.orchestrator import Orchestrator
from batman.agents.response_agent import ResponseAgent
from batman.detection.extraction import ExtractionResult
from batman.llm.provider import StubProvider
from batman.policy.engine import PolicyConfig, PolicyEngine
from batman.types import Action, DetectorResult, RuleEvent, ThreatType


def _detector(score, anomalous):
    return DetectorResult(anomalous, score, "isolation_forest", "1.0")


def test_detection_agent_builds_evidence():
    agent = DetectionAgent()
    ev = agent.analyze(
        _detector(0.3, False),
        ExtractionResult("MODEL_EXTRACTION", 0.8, ["high diversity"]),
        [],
    )
    assert ev.threat_type == ThreatType.MODEL_EXTRACTION
    assert ev.extraction_score == 0.8
    assert "high diversity" in ev.evidence


def test_investigation_agent_fallback_without_llm():
    # StubProvider triggers the deterministic fallback path.
    agent = InvestigationAgent(retriever=None, llm=StubProvider())
    ev = DetectionAgent().analyze(
        _detector(0.7, True),
        ExtractionResult("MODEL_EXTRACTION", 0.7, ["systematic variation"]),
        [],
    )
    expl = agent.investigate(ev)
    assert expl.summary
    assert expl.threat_type == "MODEL_EXTRACTION"


def test_orchestrator_llm_cannot_bypass_policy():
    # Even if the (stub) LLM recommends ALLOW, a high-severity rule must BLOCK.
    policy = PolicyEngine(PolicyConfig(), mode="enforce")
    orch = Orchestrator(
        InvestigationAgent(None, StubProvider()), ResponseAgent(policy)
    )
    ev = DetectionAgent().analyze(
        _detector(0.1, False),
        ExtractionResult("NONE", 0.0, []),
        [RuleEvent("nan_input", "high", "nan detected")],
    )
    decision = orch.handle(ev)
    assert decision.action == Action.BLOCK
