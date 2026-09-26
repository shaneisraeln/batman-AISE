"""BATMAN Python SDK.

Wrap any model to protect its inference at runtime:

    from batman import BATMAN

    shield = BATMAN(model=model, api_key="bm_live_xxx", mode="enforce")
    result = shield.predict(X)

Modes:
    monitor  -- detect and log, never block
    enforce  -- apply configured policies

The SDK shares the same SecurityEngine used by the gateway, so behavior is
identical across deployments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from batman.config import get_settings
from batman.engine import SecurityEngine
from batman.gateway.validation import ValidationConfig
from batman.types import Action, SecurityDecision


class BlockedError(Exception):
    """Raised in enforce mode when a request is blocked."""

    def __init__(self, decision: SecurityDecision):
        self.decision = decision
        super().__init__(f"Request blocked: {decision.reason}")


@dataclass
class PredictResult:
    allowed: bool
    action: str
    threat_type: str
    threat_level: str
    prediction: Any
    decision: SecurityDecision

    def to_dict(self) -> dict[str, Any]:
        d = self.decision.to_dict()
        d["prediction"] = _jsonable(self.prediction)
        return d


def _jsonable(x):
    try:
        import numpy as np

        if isinstance(x, np.ndarray):
            return x.tolist()
    except Exception:
        pass
    return x


class BATMAN:
    def __init__(
        self,
        model: Any,
        api_key: str | None = None,
        mode: str = "enforce",
        session_id: str = "sdk-session",
        project_id: str = "sdk-project",
        model_id: str = "sdk-model",
        validation_config: ValidationConfig | None = None,
        raise_on_block: bool = False,
        enable_llm: bool = True,
    ):
        self.api_key = api_key
        self.session_id = session_id
        self.project_id = project_id
        self.model_id = model_id
        self.raise_on_block = raise_on_block
        settings = get_settings()
        self.engine = SecurityEngine(
            model=model,
            settings=settings,
            validation_config=validation_config,
            mode=mode,
            enable_llm=enable_llm,
        )

    def predict(self, X: Any, session_id: str | None = None) -> PredictResult:
        decision, output, _event = self.engine.analyze_request(
            X,
            project_id=self.project_id,
            model_id=self.model_id,
            session_id=session_id or self.session_id,
            key_id=self.api_key,
            run_model=True,
        )
        allowed = decision.allowed()
        if not allowed and self.raise_on_block and decision.action == Action.BLOCK:
            raise BlockedError(decision)
        return PredictResult(
            allowed=allowed,
            action=decision.action.value,
            threat_type=decision.threat_type.value,
            threat_level=decision.threat_level.value,
            prediction=output,
            decision=decision,
        )

    def analyze(self, X: Any, session_id: str | None = None) -> SecurityDecision:
        """Run detection/policy without invoking the protected model."""
        decision, _output, _event = self.engine.analyze_request(
            X,
            project_id=self.project_id,
            model_id=self.model_id,
            session_id=session_id or self.session_id,
            key_id=self.api_key,
            run_model=False,
        )
        return decision
