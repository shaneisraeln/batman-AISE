"""Model-extraction / probing detector.

A behavioral, rule-weighted detector over session signals. It reports evidence
rather than claiming certainty. This is deliberately interpretable so the
investigation agent can explain *why* a session looks like extraction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from batman.features.session import SessionState
from batman.types import ThreatType


@dataclass
class ExtractionResult:
    threat_type: str
    score: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "threat_type": self.threat_type,
            "score": self.score,
            "evidence": list(self.evidence),
        }


class ExtractionDetector:
    """Scores extraction/probing behavior from behavioral features + session.

    Signals (each contributes a weighted amount to a [0,1] score):
    - high request rate
    - high query diversity (high unique-input ratio at volume)
    - systematic input variation (moderate similarity, not duplicates)
    - long session length
    - boundary probing (steady progression of distinct queries)
    """

    def __init__(
        self,
        rate_threshold: float = 90.0,
        min_session_for_diversity: int = 20,
    ):
        self.rate_threshold = rate_threshold
        self.min_session_for_diversity = min_session_for_diversity

    def detect(
        self, features: dict[str, float], session: SessionState
    ) -> ExtractionResult:
        evidence: list[str] = []
        score = 0.0

        rate = features.get("request_rate", 0.0)
        session_count = features.get("session_request_count", 0.0)
        unique_ratio = features.get("unique_input_ratio", 1.0)
        duplicate_ratio = features.get("duplicate_ratio", 0.0)
        similarity = features.get("query_similarity", 0.0)

        # High request volume.
        if rate >= self.rate_threshold:
            score += 0.30
            evidence.append(f"high request rate ({rate:.0f}/min)")

        # High diversity at volume: hallmark of harvesting the input space.
        if session_count >= self.min_session_for_diversity and unique_ratio >= 0.85:
            score += 0.30
            evidence.append(
                f"high query diversity (unique ratio {unique_ratio:.2f} over "
                f"{int(session_count)} queries)"
            )

        # Systematic variation: related but non-duplicate queries.
        if 0.5 <= similarity <= 0.95 and duplicate_ratio < 0.2:
            score += 0.20
            evidence.append(
                f"systematic input variation (similarity {similarity:.2f}, "
                f"low duplication {duplicate_ratio:.2f})"
            )

        # Abnormal session length.
        if session_count >= 100:
            score += 0.15
            evidence.append(f"abnormal session length ({int(session_count)} requests)")

        # Boundary probing: growing set of distinct queries at a steady cadence.
        distinct = len(session.recent_inputs)
        if distinct >= 30 and unique_ratio >= 0.8 and rate >= self.rate_threshold * 0.5:
            score += 0.05
            evidence.append("sustained boundary exploration pattern")

        score = min(1.0, score)
        threat = (
            ThreatType.MODEL_EXTRACTION.value if score > 0 else ThreatType.NONE.value
        )
        return ExtractionResult(threat_type=threat, score=score, evidence=evidence)
