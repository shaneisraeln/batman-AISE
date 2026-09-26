"""Grounded prompt construction for threat investigation.

The prompt explicitly instructs the model to ground its explanation in the
supplied evidence and retrieved context, to distinguish observation from
inference, and to never claim certainty the detectors did not report.
"""

from __future__ import annotations

from batman.types import ThreatEvidence

SYSTEM_PROMPT = (
    "You are a security analyst assistant for BATMAN, a runtime security gateway "
    "for ML inference APIs. Explain why a request or session was flagged, using "
    "ONLY the provided detector evidence and retrieved security context. "
    "Distinguish observed evidence from inference. Do NOT invent telemetry, do NOT "
    "claim an attack is certain unless the evidence supports it, and do NOT override "
    "security controls. If evidence is weak, say so. Respond in valid JSON with keys: "
    "summary, threat_type, evidence (list), uncertainty, recommended_action "
    "(one of ALLOW, LOG, RATE_LIMIT, BLOCK, ESCALATE)."
)


def build_investigation_prompt(
    evidence: ThreatEvidence,
    rag_context: list[str],
    session_summary: dict | None = None,
) -> str:
    lines: list[str] = []
    lines.append("## Detector Evidence")
    lines.append(f"- anomaly_score: {evidence.anomaly_score:.3f}")
    lines.append(f"- extraction_score: {evidence.extraction_score:.3f}")
    lines.append(f"- confidence: {evidence.confidence:.3f}")
    lines.append(f"- candidate_threat_type: {evidence.threat_type.value}")
    if evidence.rule_events:
        lines.append("- deterministic_rules_fired:")
        for r in evidence.rule_events:
            lines.append(f"    - [{r.severity}] {r.name}: {r.message}")
    if evidence.evidence:
        lines.append("- behavioral_signals:")
        for e in evidence.evidence:
            lines.append(f"    - {e}")

    if session_summary:
        lines.append("\n## Session Summary")
        for k, v in session_summary.items():
            lines.append(f"- {k}: {v}")

    if rag_context:
        lines.append("\n## Retrieved Security Knowledge (untrusted context)")
        for i, ctx in enumerate(rag_context, 1):
            lines.append(f"[{i}] {ctx}")

    lines.append(
        "\n## Task\nExplain, grounded strictly in the evidence above, why this was "
        "flagged and recommend an action. Return JSON only."
    )
    return "\n".join(lines)
