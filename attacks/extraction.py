"""Model-extraction / probing generators.

Two strategies are provided to support the generalization experiment:

- strategy "A" (grid/systematic): sweeps the input space systematically with
  high diversity and steady cadence.
- strategy "B" (boundary/adaptive): perturbs around reference samples to probe
  decision boundaries, with growing distinct-query coverage.

Ground-truth label: EXTRACTION.
"""

from __future__ import annotations

import numpy as np

from attacks.common import RequestEvent, make_rng


def generate_extraction(
    reference_data: np.ndarray,
    strategy: str = "A",
    n_sessions: int = 8,
    requests_per_session: tuple[int, int] = (80, 160),
    seed: int = 2,
) -> list[RequestEvent]:
    rng = make_rng(seed)
    ref = np.asarray(reference_data, dtype=float)
    dim = ref.shape[1]
    lo = ref.min(axis=0)
    hi = ref.max(axis=0)
    events: list[RequestEvent] = []

    for s in range(n_sessions):
        sid = f"extract_{strategy}_{seed}_{s}"
        n = int(rng.integers(requests_per_session[0], requests_per_session[1] + 1))
        for i in range(n):
            if strategy == "A":
                # Systematic uniform sweep across the feature ranges: high diversity.
                x = lo + (hi - lo) * rng.random(dim)
            else:
                # Boundary-adaptive: pick a reference sample and perturb it.
                idx = int(rng.integers(0, ref.shape[0]))
                scale = 0.05 + 0.25 * (i / max(1, n))  # growing perturbation
                x = ref[idx] + rng.normal(0, scale, size=dim)
            dt = float(rng.uniform(0.05, 0.4))  # automated, fast but not a pure flood
            events.append(
                RequestEvent(
                    x.reshape(1, -1), sid, dt, "EXTRACTION", meta={"strategy": strategy}
                )
            )
    return events
