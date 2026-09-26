"""Shared dataclasses and enums passed between BATMAN components.

These are the structured objects the TRD mandates: ThreatEvidence,
decisions, actions. Keeping them framework-free avoids circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Action(str, Enum):
    ALLOW = "ALLOW"
    LOG = "LOG"
    RATE_LIMIT = "RATE_LIMIT"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class ThreatLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNCERTAIN = "UNCERTAIN"


class ThreatType(str, Enum):
    NONE = "NONE"
    API_ABUSE = "API_ABUSE"
    MODEL_EXTRACTION = "MODEL_EXTRACTION"
    ANOMALOUS_INPUT = "ANOMALOUS_INPUT"
    INVALID_REQUEST = "INVALID_REQUEST"


@dataclass
class RuleEvent:
    """A deterministic rule that fired."""

    name: str
    severity: str  # "low" | "medium" | "high"
    message: str


@dataclass
class DetectorResult:
    is_anomalous: bool
    score: float
    detector: str
    version: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreatEvidence:
    """Aggregated, structured evidence. The policy layer maps this to actions.

    Scores are NOT blindly averaged; each signal is preserved.
    """

    anomaly_score: float = 0.0
    extraction_score: float = 0.0
    rule_events: list[RuleEvent] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    threat_type: ThreatType = ThreatType.NONE
    detector_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anomaly_score": self.anomaly_score,
            "extraction_score": self.extraction_score,
            "rule_events": [
                {"name": r.name, "severity": r.severity, "message": r.message}
                for r in self.rule_events
            ],
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "threat_type": self.threat_type.value,
            "detector_version": self.detector_version,
        }


@dataclass
class Explanation:
    """Output of the investigation agent (RAG + LLM), grounded in evidence."""

    summary: str
    threat_type: str
    evidence: list[str]
    uncertainty: str
    recommended_action: str
    rag_context: list[str] = field(default_factory=list)
    llm_available: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "threat_type": self.threat_type,
            "evidence": self.evidence,
            "uncertainty": self.uncertainty,
            "recommended_action": self.recommended_action,
            "rag_context": self.rag_context,
            "llm_available": self.llm_available,
        }


@dataclass
class SecurityDecision:
    """Final decision returned by the orchestrator/policy engine."""

    action: Action
    threat_level: ThreatLevel
    threat_type: ThreatType
    evidence: ThreatEvidence
    explanation: Explanation | None = None
    reason: str = ""

    def allowed(self) -> bool:
        return self.action in (Action.ALLOW, Action.LOG)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "threat_level": self.threat_level.value,
            "threat_type": self.threat_type.value,
            "reason": self.reason,
            "evidence": self.evidence.to_dict(),
            "explanation": self.explanation.to_dict() if self.explanation else None,
        }
