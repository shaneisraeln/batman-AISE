"""Security knowledge base seed content.

Small, curated documents covering the domains the PRD lists. Chunked into
retrievable passages. This is the corpus the retriever indexes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Document:
    doc_id: str
    category: str
    text: str


KNOWLEDGE_DOCS: list[Document] = [
    Document(
        "extraction_overview",
        "model_extraction",
        "Model extraction (model stealing) is an attack where an adversary sends "
        "many queries to a black-box ML API and uses the input-output pairs to train "
        "a surrogate model that approximates the target. Indicators include a high "
        "volume of valid queries, high query diversity that systematically covers the "
        "input space, and sustained sessions that probe decision boundaries.",
    ),
    Document(
        "extraction_signals",
        "model_extraction",
        "Behavioral signals of extraction include: sustained high request rates, a high "
        "ratio of unique inputs, systematic input variation (queries that are related "
        "but not duplicates), and long sessions. Because each individual query can be "
        "valid, extraction is best detected from the pattern across a session rather "
        "than any single request.",
    ),
    Document(
        "extraction_response",
        "response_guidance",
        "Recommended responses to suspected model extraction: rate-limit the offending "
        "session or key to slow harvesting, escalate uncertain cases for analyst review, "
        "and block only when evidence is strong. Aggressive blocking risks false positives "
        "against legitimate high-volume batch users, so prefer graduated responses.",
    ),
    Document(
        "adversarial_overview",
        "adversarial_ml",
        "Adversarial examples are inputs crafted with small perturbations to cause "
        "misclassification. Runtime signals include inputs with unusual norms, values "
        "outside expected ranges, or distribution shifts relative to normal traffic. "
        "Full adversarial defense is out of scope for a lightweight gateway; the goal is "
        "to flag anomalous inputs for review.",
    ),
    Document(
        "api_abuse_overview",
        "api_abuse",
        "API abuse includes excessive request rates, bursts, and repeated identical "
        "queries. Deterministic rate limiting handles the clearest cases. Behavioral "
        "analysis adds value by distinguishing benign bursts from sustained abusive "
        "patterns across a session.",
    ),
    Document(
        "api_abuse_response",
        "response_guidance",
        "For API abuse, apply per-key and per-session rate limits with a burst allowance. "
        "Return HTTP 429 when limits are exceeded. Hard rate-limit violations are treated "
        "as high-severity deterministic rule events that block the request.",
    ),
    Document(
        "anomalous_input_guidance",
        "response_guidance",
        "Anomalous inputs (NaN, Inf, out-of-range values, extreme norms) should be logged "
        "or blocked depending on severity. NaN and Inf are treated as high-severity because "
        "they can crash or destabilize downstream models.",
    ),
    Document(
        "policy_reference",
        "policies",
        "BATMAN policy mapping: LOW severity maps to LOG, MEDIUM to RATE_LIMIT, HIGH to "
        "BLOCK, and UNCERTAIN to ESCALATE for human review. Deterministic high-severity "
        "rules always take precedence over ML scores. Thresholds are configurable and must "
        "be calibrated against a validation set rather than assumed universal.",
    ),
    Document(
        "hitl_reference",
        "policies",
        "Human-in-the-loop review is used for uncertain or high-impact decisions. Analysts "
        "label detections as true or false positives; this feedback is stored separately "
        "from immutable telemetry and used for future evaluation, not automatic retraining.",
    ),
]


def all_chunks() -> list[Document]:
    """Return the corpus as retrievable chunks (docs are already passage-sized)."""
    return list(KNOWLEDGE_DOCS)
