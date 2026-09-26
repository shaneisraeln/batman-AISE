"""BATMAN core security engine.

Shared by both the SDK and the gateway so detection/policy behavior is identical
regardless of deployment. Orchestrates the full pipeline:

    validate -> update session -> extract features -> rules
    -> anomaly + extraction detection -> detection agent (evidence)
    -> orchestrator (investigation if needed + policy) -> decision -> telemetry
"""

from __future__ import annotations

import os
import time

import numpy as np

from batman.adapters import ModelAdapter, to_adapter
from batman.agents.detection_agent import DetectionAgent
from batman.agents.investigation_agent import InvestigationAgent
from batman.agents.orchestrator import Orchestrator
from batman.agents.response_agent import ResponseAgent
from batman.config import Settings, get_settings
from batman.detection.extraction import ExtractionDetector
from batman.detection.isolation_forest import IsolationForestDetector
from batman.detection.rules import RulesEngine
from batman.features.extractor import FeatureExtractor
from batman.features.session import SessionStore
from batman.gateway.rate_limit import SlidingWindowRateLimiter
from batman.gateway.validation import ValidationConfig, validate_request
from batman.llm.provider import get_llm_provider
from batman.policy.engine import PolicyConfig, PolicyEngine
from batman.rag.retriever import Retriever
from batman.telemetry.logger import get_logger, log_event
from batman.telemetry.schema import TelemetryEvent, new_request_id, utcnow_iso
from batman.telemetry.store import TelemetryStore
from batman.types import (
    Action,
    RuleEvent,
    SecurityDecision,
    ThreatEvidence,
    ThreatLevel,
    ThreatType,
)
from batman.version import DETECTOR_VERSION

DEFAULT_MODEL_PATH = os.path.join("models", "isolation_forest.joblib")


class SecurityEngine:
    def __init__(
        self,
        model: object | None = None,
        settings: Settings | None = None,
        store: TelemetryStore | None = None,
        detector_path: str = DEFAULT_MODEL_PATH,
        validation_config: ValidationConfig | None = None,
        mode: str | None = None,
        enable_llm: bool = True,
    ):
        self.settings = settings or get_settings()
        self.mode = mode or self.settings.mode
        self.logger = get_logger("batman.engine", self.settings.log_level)
        self.model: ModelAdapter | None = to_adapter(model) if model is not None else None

        self.store = store or TelemetryStore(self.settings.db_path)
        self.validation_config = validation_config or ValidationConfig()

        # Behavioral warmup: number of requests a session must accumulate before
        # the anomaly signal alone can escalate to a blocking action.
        self.warmup_requests = 5
        self.warmup_score_cap = 0.5

        # Detection components.
        self.anomaly_detector = IsolationForestDetector.load(detector_path)
        self.extraction_detector = ExtractionDetector()
        self.rules = RulesEngine()
        self.extractor = FeatureExtractor()
        self.sessions = SessionStore()
        self.rate_limiter = SlidingWindowRateLimiter(self.settings.rate_limit)

        # Policy + agents.
        self.policy = PolicyEngine(PolicyConfig(), mode=self.mode)
        self.detection_agent = DetectionAgent()

        retriever = None
        llm = None
        if enable_llm:
            try:
                retriever = Retriever(settings=self.settings)
            except Exception:
                retriever = None
            llm = get_llm_provider(self.settings)
        else:
            from batman.llm.provider import StubProvider

            llm = StubProvider()
        self.investigation_agent = InvestigationAgent(retriever, llm)
        self.response_agent = ResponseAgent(self.policy)
        # When a real (non-stub) LLM is active, throttle investigations per
        # session so a burst of requests doesn't fire one LLM call each.
        llm_cooldown = 4.0 if getattr(llm, "name", "stub") != "stub" else 0.0
        self.orchestrator = Orchestrator(
            self.investigation_agent, self.response_agent, llm_cooldown_s=llm_cooldown
        )

    # --- main entry point ---
    def analyze_request(
        self,
        inputs,
        project_id: str = "default",
        model_id: str = "default",
        session_id: str = "default",
        auth_error: str | None = None,
        key_id: str | None = None,
        run_model: bool = True,
    ) -> tuple[SecurityDecision, object, TelemetryEvent]:
        """Run the full pipeline. Returns (decision, model_output_or_None, event)."""
        start = time.perf_counter()
        now = time.monotonic()
        request_id = new_request_id()

        # 1) Rate limiting (deterministic floor).
        rl = self.rate_limiter.check(f"{key_id or session_id}")
        rate_limited = not rl.allowed

        # 2) Validation.
        vres = validate_request(inputs, self.validation_config)
        arr = vres.array if vres.array is not None else np.zeros((1, 1))

        # 3) Session update + feature extraction.
        session = self.sessions.get(session_id)
        session.record(ts=now, input_vec=arr[0] if arr.ndim == 2 else arr)
        feats = self.extractor.extract(arr, session, now=now)
        feat_values = feats.to_dict()

        # 4) Deterministic rules.
        rule_events = self.rules.evaluate(
            feat_values,
            validation_errors=vres.errors if not vres.ok else None,
            auth_error=auth_error,
            key_id=key_id,
        )
        if rate_limited:
            rule_events.append(
                RuleEvent("rate_limit_exceeded", "medium", rl.reason)
            )

        # 5) ML detection.
        anomaly = self.anomaly_detector.predict(feats.vector())
        session.anomaly_history.append(anomaly.score)
        extraction = self.extraction_detector.detect(feat_values, session)

        # Behavioral warmup: the anomaly detector reasons over behavioral history
        # (request rate, session count, query relationships). During the first
        # few requests of a session that history is empty, so a lone benign
        # request can look anomalous. We dampen the anomaly signal's ability to
        # BLOCK during warmup — deterministic rules and the extraction detector
        # (which requires volume) are unaffected. This reflects the PRD intent:
        # detect behavior *across* requests, not treat each request in isolation.
        warmup = feat_values.get("session_request_count", 0.0) < self.warmup_requests
        if warmup and anomaly.is_anomalous:
            anomaly.is_anomalous = False
            anomaly.extra = {**anomaly.extra, "warmup_dampened": True}
            anomaly.score = min(anomaly.score, self.warmup_score_cap)

        # 6) Detection agent builds structured evidence.
        evidence = self.detection_agent.analyze(
            anomaly, extraction, rule_events, behavioral_evidence=None
        )

        # 7) Orchestrator: investigation (if needed) + authoritative policy.
        session_summary = {
            "session_request_count": int(feat_values.get("session_request_count", 0)),
            "request_rate": round(feat_values.get("request_rate", 0.0), 2),
            "unique_input_ratio": round(feat_values.get("unique_input_ratio", 1.0), 3),
        }
        decision = self.orchestrator.handle(
            evidence, session_summary, session_key=session_id
        )

        # Rate-limit action override: if limiter tripped and no stronger action,
        # ensure at least RATE_LIMIT in enforce mode.
        if rate_limited and self.mode == "enforce":
            if decision.action in (Action.ALLOW, Action.LOG):
                decision.action = Action.RATE_LIMIT
                decision.threat_level = ThreatLevel.MEDIUM
                if decision.threat_type == ThreatType.NONE:
                    decision.threat_type = ThreatType.API_ABUSE
                decision.reason = (decision.reason + "; rate limit exceeded").strip("; ")

        # 8) Run the protected model if allowed.
        model_output = None
        if run_model and self.model is not None and decision.allowed() and vres.ok:
            try:
                model_output = self.model.predict(arr)
            except Exception as exc:  # controlled error, no internal leak
                self.logger.error("model_predict_failed")
                model_output = {"error": "model_inference_error"}
                decision.reason = (decision.reason + "; model_error").strip("; ")

        latency_ms = (time.perf_counter() - start) * 1000.0

        # 9) Telemetry (no raw inputs stored).
        event = TelemetryEvent(
            request_id=request_id,
            timestamp=utcnow_iso(),
            project_id=project_id,
            model_id=model_id,
            session_id=session_id,
            detector_version=DETECTOR_VERSION,
            features=feat_values,
            anomaly_score=evidence.anomaly_score,
            extraction_score=evidence.extraction_score,
            threat_type=decision.threat_type.value,
            threat_level=decision.threat_level.value,
            action=decision.action.value,
            latency_ms=round(latency_ms, 3),
            reason=decision.reason,
        )
        try:
            self.store.record_telemetry(event)
        except Exception:
            # Telemetry failure must not break enforcement; log locally.
            log_event(self.logger, "telemetry_store_failed", request_id=request_id)

        return decision, model_output, event
