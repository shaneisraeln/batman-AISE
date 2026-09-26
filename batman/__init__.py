"""BATMAN — Behavioral AI Threat Monitoring and Mitigation for ML Models.

A model-agnostic runtime security layer for ML inference systems.

Public API:
    from batman import BATMAN
    from batman import ModelAdapter, SklearnAdapter
"""

from batman.version import __version__
from batman.sdk import BATMAN
from batman.adapters import ModelAdapter, SklearnAdapter, CallableAdapter

__all__ = [
    "__version__",
    "BATMAN",
    "ModelAdapter",
    "SklearnAdapter",
    "CallableAdapter",
]
