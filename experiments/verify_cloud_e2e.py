"""Phase 2 live end-to-end verification: SDK -> BATMAN Cloud -> real ML service.

Full developer journey against running services:
  1. Sign up + log in (control plane).
  2. Create project, register model, point it at the REAL ml-service (:9000).
  3. Mint a BATMAN API key.
  4. Use the lightweight batman-ml SDK to send a legitimate request -> real
     prediction proxied from the upstream model.
  5. Drive a controlled extraction burst -> BATMAN detects + enforces.
  6. Confirm telemetry is tenant-scoped and traceable.
  7. Submit analyst feedback on a detected threat; confirm it lists + attaches.
  8. Confirm a revoked key is denied (401).
  9. Confirm logout (token discard) leaves protected routes unreachable (401).

Requires:  ml-service on :9000, BATMAN cloud on :8100.
Run:       python -m experiments.verify_cloud_e2e
"""

from __future__ import annotations

import sys

import httpx
import numpy as np
from sklearn.datasets import load_breast_cancer

CLOUD = "http://127.0.0.1:8100"
ML = "http://127.0.0.1:9000"


def main() -> int:
    ok = True
    admin = httpx.Client(base_url=CLOUD, timeout=30)

    # 1) signup + login
    email = f"dev+{np.random.randint(1_000_000)}@example.com"
    admin.post("/auth/signup", json={"email": email, "password": "password123"})
    token = admin.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    print(f"[1] signed up + logged in as {email}")

    # 2) project + model + upstream (point at the REAL ml-service)
    pid = admin.post("/projects", json={"name": "Diagnostics", "environment": "production"}, headers=H).json()["project_id"]
    mid = admin.post("/models", json={"project_id": pid, "name": "breast-cancer-v1"}, headers=H).json()["model_id"]
    up = admin.put(
        f"/models/{mid}/upstream",
        json={"url": f"{ML}/predict", "request_format": "instances", "response_format": "predictions"},
        headers=H,
    )
    print(f"[2] project/model created; upstream set -> {ML}/predict ({up.status_code})")

    # 3) mint API key
    key = admin.post("/keys", json={"project_id": pid, "model_id": mid, "name": "sdk"}, headers=H).json()["api_key"]
    print(f"[3] minted key {key[:14]}…")

    # 4) SDK legitimate request -> real prediction
    from batman_ml import BatmanClient

    sdk = BatmanClient(api_key=key, base_url=CLOUD)
    data = load_breast_cancer()
    r = sdk.predict([data.data[0].tolist()], session_id="sdk-normal")
    print(f"[4] SDK predict -> action={r.action} prediction={r.prediction} request_id={r.request_id[:16]}…")
    if not r.allowed or r.prediction is None:
        print("    FAIL: legit SDK request did not return a prediction"); ok = False

    # 5) controlled extraction burst -> detection/enforcement
    rng = np.random.default_rng(3)
    lo, hi = data.data.min(0), data.data.max(0)
    actions = {}
    for _ in range(120):
        vec = (lo + (hi - lo) * rng.random(data.data.shape[1])).tolist()
        try:
            res = sdk.predict([vec], session_id="CTRL-extract")
            actions[res.action] = actions.get(res.action, 0) + 1
        except Exception as e:
            actions[type(e).__name__] = actions.get(type(e).__name__, 0) + 1
    print(f"[5] extraction burst actions: {actions}")
    if not any(k in actions for k in ("BLOCK", "RATE_LIMIT", "BlockedError", "RateLimitedError")):
        print("    FAIL: extraction burst was never detected/enforced"); ok = False

    # 6) tenant-scoped telemetry
    metrics = admin.get("/v1/metrics", headers=H).json()
    threats = admin.get("/v1/threats?limit=50", headers=H).json()["threats"]
    print(f"[6] tenant metrics: total={metrics['total_requests']} active_threats={metrics['active_threats']} threat_rows={len(threats)}")
    if metrics["total_requests"] < 1:
        print("    FAIL: no tenant telemetry recorded"); ok = False

    # 7) analyst feedback (dashboard flow): label a detected threat, confirm it
    #    is listed and attached to the threat detail.
    if threats:
        rid = threats[0]["request_id"]
        fb = admin.post("/v1/feedback",
                        json={"request_id": rid, "label": "TRUE_POSITIVE", "analyst_note": "e2e verified"},
                        headers=H)
        listed = admin.get("/v1/feedback", headers=H).json()["feedback"]
        detail = admin.get(f"/v1/threats/{rid}", headers=H).json()
        got = any(f["request_id"] == rid and f["label"] == "TRUE_POSITIVE" for f in listed)
        on_detail = any(f["label"] == "TRUE_POSITIVE" for f in detail.get("feedback", []))
        print(f"[7] feedback recorded (HTTP {fb.status_code}); listed={got} on_detail={on_detail}")
        if not (fb.status_code == 200 and got and on_detail):
            print("    FAIL: feedback did not record/list/attach correctly"); ok = False
    else:
        print("[7] SKIP feedback: no threat rows to label"); ok = False

    # 8) revoked key denied
    keys = admin.get("/keys", headers=H).json()["api_keys"]
    admin.delete(f"/keys/{keys[0]['key_id']}", headers=H)
    denied = httpx.post(f"{CLOUD}/v1/predict", headers={"x-api-key": key},
                        json={"inputs": [data.data[0].tolist()]})
    print(f"[8] revoked key -> HTTP {denied.status_code} (expect 401)")
    if denied.status_code != 401:
        print("    FAIL: revoked key was not denied"); ok = False

    # 9) logout: the client discards the bearer token. The API is stateless
    #    (HMAC tokens), so "logout" is a client-side token discard — verify a
    #    fresh client with no token cannot reach a protected control-plane route.
    anon = httpx.get(f"{CLOUD}/v1/metrics")
    print(f"[9] post-logout (no token) -> HTTP {anon.status_code} (expect 401)")
    if anon.status_code != 401:
        print("    FAIL: protected route reachable without a token"); ok = False

    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
