"""Investigation Agent.

Retrieves relevant security knowledge (RAG), constructs a grounded prompt, calls
the LLM, and returns a structured Explanation. Includes a robust deterministic
fallback so that an LLM/RAG failure degrades gracefully rather than disabling
enforcement.

Treats retrieved documents and threat evidence as untrusted context: the LLM is
never given tool access and its output is parsed defensively.
"""

from __future__ import annotations

import json

from batman.llm.prompts import SYSTEM_PROMPT, build_investigation_prompt
from batman.llm.provider import LLMProvider
from batman.rag.retriever import Retriever
from batman.types import Explanation, ThreatEvidence


class InvestigationAgent:
    def __init__(self, retriever: Retriever | None, llm: LLMProvider):
        self.retriever = retriever
        self.llm = llm

    def _build_query(self, ev: ThreatEvidence) -> str:
        parts = [ev.threat_type.value.replace("_", " ")]
        parts.extend(ev.evidence[:5])
        parts.extend(r.name for r in ev.rule_events)
        return " ".join(parts)

    def investigate(
        self, ev: ThreatEvidence, session_summary: dict | None = None
    ) -> Explanation:
        rag_context: list[str] = []
        if self.retriever is not None:
            try:
                rag_context = self.retriever.retrieve(self._build_query(ev))
            except Exception:
                rag_context = []  # RAG failure => continue without context

        prompt = build_investigation_prompt(ev, rag_context, session_summary)

        llm_available = True
        parsed: dict | None = None
        try:
            raw = self.llm.generate(prompt, system=SYSTEM_PROMPT)
            parsed = self._parse_json(raw)
        except Exception:
            llm_available = False
            parsed = None

        if parsed and self.llm.name != "stub":
            return Explanation(
                summary=str(parsed.get("summary", "")).strip()
                or self._fallback_summary(ev),
                threat_type=str(parsed.get("threat_type") or ev.threat_type.value),
                evidence=list(parsed.get("evidence") or ev.evidence),
                uncertainty=str(parsed.get("uncertainty", "")),
                recommended_action=str(parsed.get("recommended_action", "ESCALATE")),
                rag_context=rag_context,
                llm_available=True,
            )

        # Deterministic fallback (stub provider or LLM failure).
        return self._fallback_explanation(ev, rag_context, llm_available)

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        if not raw:
            return None
        raw = raw.strip()
        # Strip common code-fence wrappers.
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:]
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _fallback_summary(ev: ThreatEvidence) -> str:
        return (
            f"Flagged as {ev.threat_type.value} with anomaly score "
            f"{ev.anomaly_score:.2f} and extraction score {ev.extraction_score:.2f}."
        )

    def _fallback_explanation(
        self, ev: ThreatEvidence, rag_context: list[str], llm_available: bool
    ) -> Explanation:
        evidence = list(ev.evidence)
        for r in ev.rule_events:
            evidence.append(f"rule: {r.name} ({r.severity})")
        uncertainty = (
            "LLM explanation unavailable; explanation derived deterministically from "
            "detector evidence."
            if not llm_available
            else "Deterministic explanation (no LLM configured)."
        )
        return Explanation(
            summary=self._fallback_summary(ev),
            threat_type=ev.threat_type.value,
            evidence=evidence,
            uncertainty=uncertainty,
            recommended_action="ESCALATE" if ev.confidence < 0.4 else "REVIEW",
            rag_context=rag_context,
            llm_available=llm_available,
        )
