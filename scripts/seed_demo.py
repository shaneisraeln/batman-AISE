"""Seed the telemetry store with a realistic incident for the dashboard.

Two phases:
  1. Bulk traffic (LLM OFF) — fast, realistic enforcement across normal / abuse /
     extraction / anomalous traffic. This fills the Overview + Monitoring charts.
  2. Showcase (LLM ON) — a few extraction requests run through the real Groq LLM
     so the Threat Detail view shows genuine, grounded explanations.

Run once, then start the gateway to explore in the dashboard:
    python -m scripts.seed_demo
"""

from __future__ import annotations

import os

import joblib
import numpy as np

# Ensure the bulk phase does not spin up the LLM regardless of .env.
from batman import BATMAN
from batman.config import get_settings
from attacks.abuse import generate_abuse
from attacks.anomalies import generate_anomalies
from attacks.extraction import generate_extraction
from attacks.normal import generate_normal
from training.prepare import load_reference


def _sanitize(x):
    return np.nan_to_num(np.asarray(x, dtype=float), nan=1e9, posinf=1e9, neginf=-1e9)


def main() -> None:
    settings = get_settings()
    db = settings.db_path
    if os.path.exists(db):
        os.remove(db)
        print(f"cleared {db}")

    model = joblib.load("models/demo_model.joblib")
    ref = load_reference()

    # --- Phase 1: bulk enforcement, LLM off (fast) ---
    fast = BATMAN(model=model, mode="enforce", enable_llm=False)
    counts: dict[str, int] = {}

    def tally(res):
        counts[res.action] = counts.get(res.action, 0) + 1

    print("seeding normal traffic...")
    for e in generate_normal(ref, n_sessions=12, seed=41):
        tally(fast.predict(_sanitize(e.inputs), session_id=e.session_id))
    print("seeding API abuse...")
    for e in generate_abuse(ref, n_sessions=3, seed=42):
        tally(fast.predict(_sanitize(e.inputs), session_id=e.session_id))
    print("seeding model extraction...")
    for e in generate_extraction(ref, strategy="A", n_sessions=3, seed=43):
        tally(fast.predict(_sanitize(e.inputs), session_id=e.session_id))
    print("seeding anomalous inputs...")
    for e in generate_anomalies(ref, n_sessions=3, seed=44):
        tally(fast.predict(_sanitize(e.inputs), session_id=e.session_id))
    print("bulk actions:", counts)

    # --- Phase 2: showcase with the real LLM (a few requests only) ---
    if settings.llm_provider != "stub":
        print(f"generating live LLM explanations via {settings.llm_provider}...")
        rich = BATMAN(model=model, mode="enforce", enable_llm=True)
        # Warm the session cheaply with the stub, then one decisive real call.
        from batman.llm.provider import StubProvider

        real = rich.engine.investigation_agent.llm
        rich.engine.investigation_agent.llm = StubProvider()
        ev = generate_extraction(ref, strategy="A", n_sessions=1, seed=99)
        for e in ev[:120]:
            rich.predict(_sanitize(e.inputs), session_id="LIVE-attacker")
        rich.engine.investigation_agent.llm = real
        # A few real LLM-backed decisions (cooldown throttles extras).
        rich.engine.orchestrator.llm_cooldown_s = 0.0
        for e in ev[120:123]:
            r = rich.predict(_sanitize(e.inputs), session_id="LIVE-attacker")
            expl = r.decision.explanation
            print("  live explanation ->", (expl.summary[:90] + "...") if expl else "none")
    else:
        print("LLM provider is 'stub'; skipping live explanation showcase.")

    print("\nDone. Start the gateway and open the dashboard:")
    print("  uvicorn batman.gateway.app:app --port 8000")
    print("  (dashboard) npm run dev  ->  http://localhost:5173")


if __name__ == "__main__":
    main()
