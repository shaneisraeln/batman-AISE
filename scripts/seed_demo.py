"""DEMO-ONLY dashboard seeder — ISOLATED from the real Phase-1 evaluation path.

⚠  This script is for populating a *demo* dashboard with illustrative traffic.
    It is deliberately kept separate from the real evaluation so it can NEVER be
    mistaken for real-service telemetry:

      - It writes to its OWN database (batman_demo.db), never the real batman.db.
      - Every session id is prefixed `DEMO-` so provenance is unmistakable.
      - It runs the in-process SDK against the local *demo* model (digits), which
        is NOT the real protected ML service used in Phase-1 validation.

    The real Phase-1 evaluation traffic comes exclusively from
    experiments/normal_client.py and experiments/attack_client.py, which send
    real HTTP requests through the live gateway to the real ML service and are
    fully request-id traceable. Do NOT use this seeder for validation metrics.

Run:
    python -m scripts.seed_demo            # writes batman_demo.db
    # then run a gateway pointed at that DB to view the demo dashboard:
    #   $env:BATMAN_DB_PATH="batman_demo.db"; uvicorn batman.gateway.app:app --port 8000
"""

from __future__ import annotations

import os

import joblib
import numpy as np

DEMO_DB = "batman_demo.db"
# Force the demo DB BEFORE importing anything that reads settings.
os.environ["BATMAN_DB_PATH"] = DEMO_DB
os.environ.setdefault("BATMAN_LLM_PROVIDER", "stub")

from batman import BATMAN  # noqa: E402
from batman.config import get_settings  # noqa: E402
from attacks.abuse import generate_abuse  # noqa: E402
from attacks.anomalies import generate_anomalies  # noqa: E402
from attacks.extraction import generate_extraction  # noqa: E402
from attacks.normal import generate_normal  # noqa: E402
from training.prepare import load_reference  # noqa: E402

DEMO_PREFIX = "DEMO-"


def _sanitize(x):
    return np.nan_to_num(np.asarray(x, dtype=float), nan=1e9, posinf=1e9, neginf=-1e9)


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.db_path == DEMO_DB, "seeder must use the isolated demo DB"

    if os.path.exists(DEMO_DB):
        os.remove(DEMO_DB)
        print(f"cleared {DEMO_DB}")

    model = joblib.load("models/demo_model.joblib")
    ref = load_reference("digits")

    demo = BATMAN(model=model, mode="enforce", enable_llm=False)
    counts: dict[str, int] = {}

    def tally(res):
        counts[res.action] = counts.get(res.action, 0) + 1

    print("[demo] normal traffic...")
    for e in generate_normal(ref, n_sessions=12, seed=41):
        tally(demo.predict(_sanitize(e.inputs), session_id=f"{DEMO_PREFIX}{e.session_id}"))
    print("[demo] API abuse...")
    for e in generate_abuse(ref, n_sessions=3, seed=42):
        tally(demo.predict(_sanitize(e.inputs), session_id=f"{DEMO_PREFIX}{e.session_id}"))
    print("[demo] model extraction...")
    for e in generate_extraction(ref, strategy="A", n_sessions=3, seed=43):
        tally(demo.predict(_sanitize(e.inputs), session_id=f"{DEMO_PREFIX}{e.session_id}"))
    print("[demo] anomalous inputs...")
    for e in generate_anomalies(ref, n_sessions=3, seed=44):
        tally(demo.predict(_sanitize(e.inputs), session_id=f"{DEMO_PREFIX}{e.session_id}"))

    print("demo actions:", counts)
    print(f"\nDemo telemetry written to {DEMO_DB} (all sessions prefixed '{DEMO_PREFIX}').")
    print("This is DEMO data — separate from the real Phase-1 evaluation DB (batman.db).")


if __name__ == "__main__":
    main()
