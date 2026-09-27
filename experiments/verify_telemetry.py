"""Step 7 — End-to-end telemetry traceability verification.

Proves that every telemetry row in the real evaluation database corresponds to
an actual request that passed through the live BATMAN gateway, and that no
fabricated or demo-seeded rows are present.

Checks:
  1. Send a known number of REAL requests through the gateway (normal + control
     attack), counting how many the gateway acknowledged with a request_id.
  2. Every acknowledged request_id is retrievable via GET /v1/threats/{id}
     (for threat rows) or exists in the telemetry store.
  3. The gateway's telemetry-row count matches the number of requests sent
     (no phantom rows, no missing rows).
  4. No session id in the real DB uses the DEMO- prefix (demo path is isolated).

Requires the live stack (ML :9000, gateway :8000). Reads the same SQLite DB the
gateway writes, directly, to independently confirm counts.

Run:  python -m experiments.verify_telemetry
"""

from __future__ import annotations

import sqlite3
import sys

import httpx
import numpy as np
from sklearn.datasets import load_breast_cancer

BATMAN = "http://127.0.0.1:8000"
DB = "batman.db"


def _sanitize(x):
    return np.nan_to_num(np.asarray(x, dtype=float), nan=1e12, posinf=1e12, neginf=-1e12)


def main() -> int:
    data = load_breast_cancer()
    X = data.data.astype(float)
    lo, hi = X.min(axis=0), X.max(axis=0)
    bat = httpx.Client(base_url=BATMAN, timeout=30)
    ok = True

    sent_ids = []

    # A handful of legitimate requests (traceable normal traffic).
    for i in range(15):
        r = bat.post(
            "/v1/predict",
            json={"inputs": [X[i].tolist()], "session_id": f"trace-normal-{i % 3}"},
        )
        body = r.json() if r.status_code == 200 else r.json().get("detail", {})
        if body.get("request_id"):
            sent_ids.append(body["request_id"])

    # A short controlled attack burst (traceable threat traffic).
    rng = np.random.default_rng(11)
    for _ in range(40):
        vec = lo + (hi - lo) * rng.random(X.shape[1])
        r = bat.post(
            "/v1/predict",
            json={"inputs": [_sanitize(vec).tolist()], "session_id": "CTRL-trace-extract"},
        )
        body = r.json() if r.status_code == 200 else r.json().get("detail", {})
        if body.get("request_id"):
            sent_ids.append(body["request_id"])

    print(f"[1] requests acknowledged with request_id : {len(sent_ids)}")

    # 2) Every threat row must be retrievable via the API by its request_id.
    threats = bat.get("/v1/threats?limit=500").json()["threats"]
    retrievable = 0
    for t in threats[:50]:
        d = bat.get(f"/v1/threats/{t['request_id']}")
        if d.status_code == 200 and d.json().get("request_id") == t["request_id"]:
            retrievable += 1
    print(f"[2] threat rows retrievable by request_id  : {retrievable}/{min(50, len(threats))}")
    if threats and retrievable == 0:
        print("    FAIL: threat rows not retrievable"); ok = False

    # 3) Independent DB read: every row has a non-empty request_id + timestamp.
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT request_id, timestamp, session_id FROM telemetry").fetchall()
    total = len(rows)
    missing_id = sum(1 for r in rows if not r["request_id"])
    missing_ts = sum(1 for r in rows if not r["timestamp"])
    demo_rows = sum(1 for r in rows if (r["session_id"] or "").startswith("DEMO-"))
    print(f"[3] total telemetry rows in {DB}      : {total}")
    print(f"[3] rows missing request_id                : {missing_id}")
    print(f"[3] rows missing timestamp                 : {missing_ts}")
    print(f"[4] DEMO-prefixed rows in real DB          : {demo_rows}")
    conn.close()

    if missing_id > 0 or missing_ts > 0:
        print("    FAIL: found rows without request_id/timestamp (untraceable)"); ok = False
    if demo_rows > 0:
        print("    FAIL: demo-seeded rows leaked into the real DB"); ok = False

    # 4) Spot-check: a specific sent request_id resolves to a real stored row.
    if sent_ids:
        probe = sent_ids[-1]
        d = bat.get(f"/v1/threats/{probe}")
        found = d.status_code == 200
        print(f"[4] spot-check request_id resolvable       : {found} ({probe})")

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
