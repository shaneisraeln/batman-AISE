"""Detector interface."""

from __future__ import annotations

import numpy as np

from batman.types import DetectorResult


class Detector:
    def predict(self, features: np.ndarray) -> DetectorResult:
        raise NotImplementedError
