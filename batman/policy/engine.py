"""Policy engine.

The policy engine is authoritative. It maps structured ThreatEvidence to a
threat level and an action. It does NOT blindly average scores; each signal is
considered, with deterministic rules taking precedence.

Level mapping (thresholds are configurable and must be calibrated):
    LOW       -> LOG
    MEDIUM    -> RATE_LIMIT
    HIGH      -> BLOCK
    UNCERTAIN -> ESCALATE
"""

from __future__ import annotations

from dataclasses import dataclass

from batman.types import Action, RuleEvent, ThreatEvidence, ThreatLevel, ThreatType


@dataclass
class PolicyConfig:
    # Score bands for the combined behavioral signal.
    low_threshold: float = 0.4
    medium_threshold: float = 0.6
    high_threshold: float = 0.8
    # Below this confidence, escalate rather than auto-act on borderline cases.
    uncertain_confidence: float = 0.35
    uncertain_band: tuple[float, float] = (0.55, 0.65)


class PolicyEngine:
    LEVEL_ACTION = {
        ThreatLevel.NONE: Action.ALLOW,
        ThreatLevel.LOW: Action.LOG,
        ThreatLevel.MEDIUM: Action.RATE_LIMIT,
        ThreatLevel.HIGH: Action.BLOCK,
        ThreatLevel.UNCERTAIN: Action.ESCALATE,
    }

    def __init__(self, config: PolicyConfig | None = None, mode: str = "enforce"):
        self.config = config or PolicyConfig()
        self.mode = mode

    def _has_high_severity_rule(self, rules: list[RuleEvent]) -> bool:
        return any(r.severity == "high" for r in rules)

    def _has_medium_severity_rule(self, rules: list[RuleEvent]) -> bool:
        return any(r.severity == "medium" for r in rules)

    def _combined_score(self, ev: ThreatEvidence) -> float:
        # Take the strongest behavioral signal rather than averaging, so a
        # strong extraction signal is not diluted by a quiet anomaly score.
        return max(ev.anomaly_score, ev.extraction_score)

    def evaluate(self, ev: ThreatEvidence) -> tuple[ThreatLevel, Action, str]:
        cfg = self.config

        # 1) Deterministic rules take precedence.
        if self._has_high_severity_rule(ev.rule_events):
            names = ", ".join(r.name for r in ev.rule_events if r.severity == "high")
            return ThreatLevel.HIGH, self._enforced(Action.BLOCK), f"high-severity rule(s): {names}"

        score = self._combined_score(ev)

        # 2) Uncertain band with low confidence -> escalate to a human.
        lo, hi = cfg.uncertain_band
        if lo <= score <= hi and ev.confidence < cfg.uncertain_confidence:
            return (
                ThreatLevel.UNCERTAIN,
                self._enforced(Action.ESCALATE),
                f"borderline score {score:.2f} with low confidence {ev.confidence:.2f}",
            )

        # 3) Score bands.
        if score >= cfg.high_threshold:
            return ThreatLevel.HIGH, self._enforced(Action.BLOCK), f"high threat score {score:.2f}"
        if score >= cfg.medium_threshold:
            return ThreatLevel.MEDIUM, self._enforced(Action.RATE_LIMIT), f"medium threat score {score:.2f}"
        if score >= cfg.low_threshold or self._has_medium_severity_rule(ev.rule_events):
            return ThreatLevel.LOW, Action.LOG, f"low threat score {score:.2f}"

        return ThreatLevel.NONE, Action.ALLOW, "no significant threat signal"

    def _enforced(self, action: Action) -> Action:
        """In monitor mode, downgrade blocking actions to LOG (detect, don't block)."""
        if self.mode == "monitor" and action in (
            Action.RATE_LIMIT,
            Action.BLOCK,
        ):
            return Action.LOG
        return action
