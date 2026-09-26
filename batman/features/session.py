"""Bounded per-client/session state.

Keeps only the last N requests and a short time horizon, so memory stays
bounded regardless of traffic volume.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

MAX_REQUESTS = 100
TIME_HORIZON_S = 300.0  # 5 minutes


@dataclass
class SessionState:
    session_id: str
    request_count: int = 0
    timestamps: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))
    recent_features: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))
    recent_inputs: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))
    anomaly_history: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))
    prediction_history: deque = field(default_factory=lambda: deque(maxlen=MAX_REQUESTS))

    def record(
        self,
        ts: float,
        features: dict | None = None,
        input_vec: np.ndarray | None = None,
        anomaly_score: float | None = None,
        prediction=None,
    ) -> None:
        self.request_count += 1
        self.timestamps.append(ts)
        if features is not None:
            self.recent_features.append(features)
        if input_vec is not None:
            self.recent_inputs.append(np.asarray(input_vec, dtype=float).ravel())
        if anomaly_score is not None:
            self.anomaly_history.append(anomaly_score)
        if prediction is not None:
            self.prediction_history.append(prediction)

    def recent_request_rate(self, now: float, window: float = 60.0) -> float:
        """Requests per minute over a rolling window."""
        cnt = sum(1 for t in self.timestamps if t > now - window)
        return cnt * (60.0 / window)

    def inter_request_time(self, now: float) -> float:
        if not self.timestamps:
            return 0.0
        return max(0.0, now - self.timestamps[-1])

    def previous_anomaly_count(self, threshold: float = 0.6) -> int:
        return sum(1 for s in self.anomaly_history if s >= threshold)


class SessionStore:
    """Thread-safe registry of session states with idle eviction."""

    def __init__(self, max_sessions: int = 10000):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.Lock()
        self._max_sessions = max_sessions

    def get(self, session_id: str) -> SessionState:
        with self._lock:
            st = self._sessions.get(session_id)
            if st is None:
                if len(self._sessions) >= self._max_sessions:
                    self._evict_idle()
                st = SessionState(session_id=session_id)
                self._sessions[session_id] = st
            return st

    def _evict_idle(self) -> None:
        # Drop the oldest-active 10% by last timestamp.
        now = time.monotonic()
        ranked = sorted(
            self._sessions.items(),
            key=lambda kv: kv[1].timestamps[-1] if kv[1].timestamps else 0,
        )
        for sid, st in ranked[: max(1, len(ranked) // 10)]:
            if not st.timestamps or st.timestamps[-1] < now - TIME_HORIZON_S:
                self._sessions.pop(sid, None)

    def reset(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._sessions.clear()
            else:
                self._sessions.pop(session_id, None)
