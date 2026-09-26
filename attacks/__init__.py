"""Controlled attack/traffic simulators for BATMAN evaluation.

Each generator yields a sequence of (input_vector, meta) events representing a
client session. Generators are seeded for reproducibility.
"""

from attacks.normal import generate_normal
from attacks.abuse import generate_abuse
from attacks.extraction import generate_extraction
from attacks.anomalies import generate_anomalies

__all__ = [
    "generate_normal",
    "generate_abuse",
    "generate_extraction",
    "generate_anomalies",
]
