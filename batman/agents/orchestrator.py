"""Agent Orchestrator.

A lightweight, deterministic workflow:

    Detection Evidence
           v
    Detection Agent  (already produced ThreatEvidence)
           v
    Need Investigation?
       |-- No  --> Response Agent
       '-- Yes --> Investigation Agent (RAG + LLM) --> Response Agent

The orchestrator never lets the LLM bypass deterministic controls: the response
agent always consults the authoritative policy engine.
"""

from __future__ import annotations

import time

from batman.agents.investigation_agent import InvestigationAgent
from batman.agents.response_agent import ResponseAgent
from batman.types import SecurityDecision, ThreatEvidence, ThreatType


class Orchestrator:
    def __init__(
        self,
        investigation_agent: InvestigationAgent,
        response_agent: ResponseAgent,
        investigate_confidence_ceiling: float = 0.95,
        llm_cooldown_s: float = 0.0,
    ):
        self.investigation_agent = investigation_agent
        self.response_agent = response_agent
        self.investigate_confidence_ceiling = investigate_confidence_ceiling
        # Per-session cooldown between LLM investigations. The PRD notes LLM
        # latency should not gate every inference request; a cooldown keeps the
        # security decision (rules + ML + policy) on the fast path while the LLM
        # explanation is refreshed periodically rather than on every request.
        self.llm_cooldown_s = llm_cooldown_s
        self._last_investigation: dict[str, float] = {}

    def _needs_investigation(self, ev: ThreatEvidence) -> bool:
        # Investigate when there is a meaningful threat signal but the case is
        # not a trivial, unambiguous deterministic block.
        if ev.threat_type == ThreatType.NONE:
            return False
        signal = max(ev.anomaly_score, ev.extraction_score)
        if signal >= 0.4:
            return True
        # High-severity rules with a clear cause don't require LLM narration,
        # but medium/uncertain cases benefit from investigation.
        return bool(ev.rule_events) and ev.confidence < self.investigate_confidence_ceiling

    def _cooldown_active(self, session_key: str | None) -> bool:
        if not self.llm_cooldown_s or session_key is None:
            return False
        last = self._last_investigation.get(session_key)
        now = time.monotonic()
        if last is not None and (now - last) < self.llm_cooldown_s:
            return True
        self._last_investigation[session_key] = now
        return False

    def handle(
        self,
        ev: ThreatEvidence,
        session_summary: dict | None = None,
        session_key: str | None = None,
    ) -> SecurityDecision:
        explanation = None
        if self._needs_investigation(ev) and not self._cooldown_active(session_key):
            explanation = self.investigation_agent.investigate(ev, session_summary)
        return self.response_agent.decide(ev, explanation)
