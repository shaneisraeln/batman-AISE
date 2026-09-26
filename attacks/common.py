"""Shared helpers for the attack simulators."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class RequestEvent:
    """One simulated inference request."""

    inputs: np.ndarray
    session_id: str
    dt: float  # seconds since previous request in the session
    label: str  # ground-truth traffic class
    meta: dict = field(default_factory=dict)

    def as_tuple(self):
        return self.inputs, self.session_id, self.dt, self.label


def make_rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
