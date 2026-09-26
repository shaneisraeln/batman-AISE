"""Model adapters. BATMAN protects any callable model via a generic interface.

The security engine must not depend on a specific ML framework.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np


class ModelAdapter:
    """Generic protected-model interface."""

    def predict(self, inputs: Any) -> Any:
        raise NotImplementedError

    def predict_proba(self, inputs: Any) -> Any | None:
        """Optional. Returns per-class probabilities if the model supports it."""
        return None


class SklearnAdapter(ModelAdapter):
    """Wraps a scikit-learn estimator."""

    def __init__(self, model: Any):
        self.model = model

    def predict(self, inputs: Any) -> Any:
        return self.model.predict(np.asarray(inputs))

    def predict_proba(self, inputs: Any) -> Any | None:
        if hasattr(self.model, "predict_proba"):
            try:
                return self.model.predict_proba(np.asarray(inputs))
            except Exception:
                return None
        return None


class CallableAdapter(ModelAdapter):
    """Wraps an arbitrary callable ``f(inputs) -> predictions``."""

    def __init__(
        self,
        fn: Callable[[Any], Any],
        proba_fn: Callable[[Any], Any] | None = None,
    ):
        self.fn = fn
        self.proba_fn = proba_fn

    def predict(self, inputs: Any) -> Any:
        return self.fn(inputs)

    def predict_proba(self, inputs: Any) -> Any | None:
        if self.proba_fn is not None:
            try:
                return self.proba_fn(inputs)
            except Exception:
                return None
        return None


def to_adapter(model: Any) -> ModelAdapter:
    """Coerce a user-supplied model into a ModelAdapter."""
    if isinstance(model, ModelAdapter):
        return model
    if hasattr(model, "predict"):
        return SklearnAdapter(model)
    if callable(model):
        return CallableAdapter(model)
    raise TypeError(
        "model must be a ModelAdapter, have a .predict() method, or be callable"
    )
