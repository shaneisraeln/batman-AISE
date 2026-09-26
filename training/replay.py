"""Replay simulated request events through BATMAN's feature pipeline.

This produces the behavioral feature rows the detectors train and evaluate on,
using the exact same FeatureExtractor + SessionStore the runtime uses. That
consistency is what makes the offline metrics meaningful.
"""

from __future__ import annotations

import numpy as np

from attacks.common import RequestEvent
from batman.features.behavioral import FEATURE_ORDER
from batman.features.extractor import FeatureExtractor
from batman.features.session import SessionStore


def replay_events(events: list[RequestEvent]) -> tuple[np.ndarray, list[str], list[dict]]:
    """Return (feature_matrix, labels, feature_dicts) in the canonical order.

    A virtual clock advances by each event's ``dt`` per session, so request-rate
    features reflect the simulated cadence deterministically.
    """
    extractor = FeatureExtractor()
    sessions = SessionStore()
    session_clock: dict[str, float] = {}

    rows: list[np.ndarray] = []
    labels: list[str] = []
    dicts: list[dict] = []

    for ev in events:
        now = session_clock.get(ev.session_id, 0.0) + ev.dt
        session_clock[ev.session_id] = now

        arr = np.asarray(ev.inputs, dtype=float)
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)

        session = sessions.get(ev.session_id)
        session.record(ts=now, input_vec=arr[0])
        feats = extractor.extract(arr, session, now=now)
        # Feed anomaly history a neutral value to mirror runtime ordering.
        session.anomaly_history.append(0.0)

        rows.append(feats.vector())
        labels.append(ev.label)
        dicts.append(feats.to_dict())

    matrix = np.vstack(rows) if rows else np.empty((0, len(FEATURE_ORDER)))
    return matrix, labels, dicts
