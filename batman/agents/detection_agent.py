"""Detection Agent.

Consumes detector outputs (anomaly + extraction) and rule events, combines the
evidence, identifies the most likely threat type, computes a confidence, and
produces a structured ThreatEvidence object. It does not call the LLM.
"""

from __future__ import annotations

from batman.detection.extraction import ExtractionResult
from batman.types import DetectorResult, RuleEvent, ThreatEvidence, ThreatType
from batman.version import DETECTOR_VERSION


class DetectionAgent:
    def analyze(
        self,
        anomaly: DetectorResult,
        extraction: ExtractionResult,
        rule_events: list[RuleEvent],
        behavioral_evidence: list[str] | None = None,
    ) -> ThreatEvidence:
        evidence_list: list[str] = list(behavioral_evidence or [])
        evidence_list.extend(extraction.evidence)

        # Decide the dominant threat type.
        threat_type = ThreatType.NONE
        if any(r.name in {"nan_input", "inf_input", "malformed_input"} for r in rule_events):
            threat_type = ThreatType.ANOMALOUS_INPUT
        if any(r.name in {"invalid_authentication", "known_blocked_key"} for r in rule_events):
            threat_type = ThreatType.INVALID_REQUEST
        if any(r.name == "hard_rate_limit" for r in rule_events):
            threat_type = ThreatType.API_ABUSE

        # Behavioral signals may override to a more specific ML-detected threat.
        # A meaningful extraction signal names the threat MODEL_EXTRACTION even
        # when the anomaly detector also fires, since extraction is the more
        # specific, actionable diagnosis. Malformed-input rules (NaN/Inf) still
        # keep their ANOMALOUS_INPUT/INVALID_REQUEST label set above.
        rule_forced = threat_type in (
            ThreatType.ANOMALOUS_INPUT,
            ThreatType.INVALID_REQUEST,
        )
        if extraction.score >= 0.5 and not rule_forced:
            threat_type = ThreatType.MODEL_EXTRACTION
        elif anomaly.is_anomalous and threat_type == ThreatType.NONE:
            threat_type = ThreatType.ANOMALOUS_INPUT
            evidence_list.append(f"anomaly detector flagged (score {anomaly.score:.2f})")

        # Confidence: agreement between signals + strength + rule corroboration.
        signals = [anomaly.score, extraction.score]
        strength = max(signals)
        agreement = 1.0 - abs(anomaly.score - extraction.score)
        rule_boost = 0.3 if any(r.severity == "high" for r in rule_events) else 0.0
        confidence = min(1.0, 0.5 * strength + 0.2 * agreement + rule_boost)

        return ThreatEvidence(
            anomaly_score=round(anomaly.score, 4),
            extraction_score=round(extraction.score, 4),
            rule_events=rule_events,
            confidence=round(confidence, 4),
            evidence=evidence_list,
            threat_type=threat_type,
            detector_version=DETECTOR_VERSION,
        )
