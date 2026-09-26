"""Deterministic rules engine.

Rules are independent from the LLM and always run, providing the security floor
that remains active even if ML/LLM/RAG fail.
"""

from __future__ import annotations

from batman.features.behavioral import FEATURE_ORDER
from batman.types import RuleEvent


class RulesEngine:
    def __init__(
        self,
        hard_rate_limit_rpm: float = 240.0,
        max_input_norm: float | None = None,
        blocked_keys: set[str] | None = None,
    ):
        self.hard_rate_limit_rpm = hard_rate_limit_rpm
        self.max_input_norm = max_input_norm
        self.blocked_keys = blocked_keys or set()

    def evaluate(
        self,
        features: dict[str, float],
        validation_errors: list[str] | None = None,
        auth_error: str | None = None,
        key_id: str | None = None,
    ) -> list[RuleEvent]:
        events: list[RuleEvent] = []

        if auth_error:
            events.append(
                RuleEvent("invalid_authentication", "high", f"auth failed: {auth_error}")
            )

        if key_id and key_id in self.blocked_keys:
            events.append(RuleEvent("known_blocked_key", "high", "key is blocklisted"))

        for err in validation_errors or []:
            sev = "high" if err.startswith(("nan", "inf", "payload")) else "medium"
            events.append(RuleEvent("malformed_input", sev, err))

        rate = features.get("request_rate", 0.0)
        if rate >= self.hard_rate_limit_rpm:
            events.append(
                RuleEvent(
                    "hard_rate_limit",
                    "high",
                    f"request_rate {rate:.0f} >= {self.hard_rate_limit_rpm:.0f} rpm",
                )
            )

        if features.get("nan_count", 0) > 0:
            events.append(RuleEvent("nan_input", "high", "input contains NaN"))
        if features.get("inf_count", 0) > 0:
            events.append(RuleEvent("inf_input", "high", "input contains Inf"))

        if self.max_input_norm is not None:
            if features.get("input_norm", 0.0) > self.max_input_norm:
                events.append(
                    RuleEvent("oversized_input_norm", "medium", "input norm out of range")
                )

        return events
