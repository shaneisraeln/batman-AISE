"""Response Agent.

Receives structured evidence and (optionally) an LLM recommendation, then asks
the authoritative policy engine for the final action. The LLM may recommend, but
the policy engine decides. The response agent only chooses policy-permitted
actions.
"""

from __future__ import annotations

from batman.policy.engine import PolicyEngine
from batman.types import (
    Action,
    Explanation,
    SecurityDecision,
    ThreatEvidence,
    ThreatLevel,
)


class ResponseAgent:
    def __init__(self, policy: PolicyEngine):
        self.policy = policy

    def decide(
        self, ev: ThreatEvidence, explanation: Explanation | None = None
    ) -> SecurityDecision:
        level, action, reason = self.policy.evaluate(ev)

        # The LLM recommendation is advisory only and is recorded, never
        # allowed to weaken a deterministic decision.
        if explanation is not None and explanation.recommended_action:
            reason = f"{reason}; llm_recommended={explanation.recommended_action}"

        return SecurityDecision(
            action=action,
            threat_level=level,
            threat_type=ev.threat_type,
            evidence=ev,
            explanation=explanation,
            reason=reason,
        )
