"""End-to-end demo driver.

Drives the recommended demo scenario from the TRD:
  1. Normal users send requests -> ALLOW.
  2. An attacker starts systematic probing (model extraction).
  3. Behavioral detector flags the session.
  4. Agents + policy escalate to RATE_LIMIT / BLOCK.
  5. Telemetry is written so the dashboard shows the incident.

Run against the SDK/engine directly (no server needed):
    python -m scripts.demo

Or, if the gateway is running, hit the HTTP API:
    python -m scripts.demo --http http://localhost:8000
"""

from __future__ import annotations

import argparse
import time

import joblib
import numpy as np

from attacks.abuse import generate_abuse
from attacks.anomalies import generate_anomalies
from attacks.extraction import generate_extraction
from attacks.normal import generate_normal
from training.prepare import load_reference


def run_local() -> None:
    from batman import BATMAN

    model = joblib.load("models/demo_model.joblib")
    ref = load_reference()
    shield = BATMAN(model=model, api_key="bm_live_demo", mode="enforce", enable_llm=True)

    counts = {}

    def tally(res):
        counts[res.action] = counts.get(res.action, 0) + 1

    print("== 1) Normal traffic ==")
    for e in generate_normal(ref, n_sessions=6, seed=11):
        tally(shield.predict(e.inputs, session_id=e.session_id))

    print("== 2) API abuse (high-rate) ==")
    for e in generate_abuse(ref, n_sessions=2, seed=12):
        tally(shield.predict(e.inputs, session_id=e.session_id))

    print("== 3) Model extraction / probing ==")
    for e in generate_extraction(ref, strategy="A", n_sessions=2, seed=13):
        tally(shield.predict(e.inputs, session_id=e.session_id))

    print("== 4) Anomalous inputs ==")
    for e in generate_anomalies(ref, n_sessions=2, seed=14):
        tally(shield.predict(e.inputs, session_id=e.session_id))

    print("\nActions summary:", counts)
    print("Telemetry written to the configured SQLite DB. Open the dashboard to inspect.")


def run_http(base: str) -> None:
    import httpx

    ref = load_reference()
    client = httpx.Client(base_url=base, timeout=30.0)
    print("health:", client.get("/v1/health").json())

    counts = {}

    def send(inputs, session_id):
        arr = np.asarray(inputs, dtype=float)
        # JSON cannot represent NaN/Inf. Map them to sentinel out-of-range values
        # so the gateway's validation layer sees and rejects them, mirroring how
        # a real client would transmit malformed numeric payloads.
        arr = np.nan_to_num(arr, nan=1e9, posinf=1e9, neginf=-1e9)
        r = client.post(
            "/v1/predict",
            json={"inputs": arr.tolist(), "session_id": session_id},
        )
        if r.status_code == 403:
            counts["BLOCK"] = counts.get("BLOCK", 0) + 1
            return
        body = r.json()
        act = body.get("action", "?")
        counts[act] = counts.get(act, 0) + 1

    for e in generate_normal(ref, n_sessions=4, seed=21):
        send(e.inputs, e.session_id)
    for e in generate_extraction(ref, strategy="A", n_sessions=2, seed=22):
        send(e.inputs, e.session_id)
    for e in generate_anomalies(ref, n_sessions=2, seed=23):
        send(e.inputs, e.session_id)

    print("Actions summary:", counts)
    print("metrics:", client.get("/v1/metrics").json())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--http", default=None, help="Gateway base URL, e.g. http://localhost:8000")
    args = p.parse_args()
    if args.http:
        run_http(args.http)
    else:
        run_local()
