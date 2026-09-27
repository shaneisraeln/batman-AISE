# BATMAN — Phase 2 Complete (Productization)

Phase 2 turned the validated Phase 1 detection engine into a usable, deployable
product. **The Phase 1 detection engine was not modified** — its 49 tests remain
green throughout.

## Final developer journey (all working, live-verified)

```
BATMAN website  →  Sign up  →  Create project  →  Register model  →  Generate API key
                                                                          │
                                            ┌─────────────────────────────┴──────────────┐
                                            ▼                                             ▼
                                     Python SDK (batman-ml)                        REST / gateway
                                            │                                             │
                                            ▼                                             ▼
                                      Python ML app                             Existing ML API
                                            └──────────────────┬──────────────────────────┘
                                                               ▼
                                                        BATMAN Cloud
                                                     (detection · policy)
                                                               ▼
                                                        Protected model
                                                               ▼
                                                          Telemetry
                                                               ▼
                                                          Dashboard
```

## What shipped

| Component | Where | Status |
|---|---|---|
| Lightweight SDK client | `sdk/` (`batman-ml`, import `batman_ml`) | built, tested, clean-install verified |
| Persistence (SQLite dev / PostgreSQL prod) | `batman/db/` | verified live on Postgres in Docker |
| Users / projects / models / keys + tenancy | `batman/cloud/service.py`, `batman/db/` | tenant isolation tested |
| Secure auth + upstream-cred encryption | `batman/cloud/crypto.py` | PBKDF2, HMAC tokens, Fernet |
| Hosted API (control + data plane) | `batman/cloud/app.py` | reuses Phase 1 engine, no detector duplication |
| Existing-ML-API protection | `batman/cloud/upstream.py` | encrypted upstream config + proxy |
| Professional dashboard | `dashboard/` | auth-gated, real data, env + CONTROLLED-TEST labels |
| Public landing page | `landing/` | honest positioning, no overclaiming |
| Developer documentation | `landing/docs/` | 15 sections, endpoint-accurate |
| Deployment infra | `Dockerfile.cloud`, `docker-compose.cloud.yml`, `deploy/Caddyfile` | built + ran on real Postgres |
| Security audit | `docs/PHASE2_SECURITY_AUDIT.md` | 10 controls, each test-cited |

## Verification highlights (all real, executed)

- **SDK is genuinely lightweight**: fresh-venv wheel install pulls only `httpx`;
  importing `batman_ml` loads zero heavy modules (no sklearn/numpy/fastapi).
- **PostgreSQL end-to-end**: containerized stack created all 7 tables and ran a
  full signup → key → predict → metrics flow on Postgres.
- **Live product E2E** (`experiments/verify_cloud_e2e.py`): SDK → cloud → real
  ML service returned a real prediction; a controlled extraction burst was
  detected and enforced (rate-limited + blocked); revoked key → 401.
- **Tests**: 103 passing (84 server/main + 13 SDK + 6 ML-service). Phase 1's 49
  tests unchanged and green.
- **twine check** PASSED on sdist + wheel; wheel contains only source + metadata
  (no secrets).

## Security posture (summary)

API keys hashed (SHA-256, constant-time verify, shown once, revocable);
passwords PBKDF2; stateless signed tokens; strict tenant isolation on every
read/write; upstream credentials Fernet-encrypted and fail-closed; input
validation; per-key/session + control-plane rate limiting; HTTPS at the proxy;
LLM advisory only — policy engine authoritative; blocked requests never reach
the model. Full detail: `docs/PHASE2_SECURITY_AUDIT.md`.

## PyPI release

Build + checks are complete and documented in `sdk/RELEASE.md`. Publishing is a
deliberate owner action requiring a PyPI token and is intentionally **not
performed here**. Exact commands:

```bash
cd sdk && python -m build && python -m twine check dist/*
# owner action, with a PyPI API token:
export TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-XXXX
python -m twine upload dist/*
```

## Honest limitations (carried through the product)

BATMAN reduces risk; it does not eliminate it. It does not protect against every
attack, guarantee perfect detection or zero false positives, or replace a
WAF/SIEM/IAM. Detection thresholds must be calibrated per protected model — run
in `monitor` mode first. Session/rate-limit state is in-process (move to Redis
for multi-replica); stateless tokens need a denylist for instant revocation.

## Run it

```bash
# Phase-2 cloud stack (Postgres + API + dashboard + landing + HTTPS proxy)
cp .env.cloud.example .env   # fill strong secrets
docker compose -f docker-compose.cloud.yml up --build
#   landing  → /        dashboard → /app        API → /v1,/auth,/projects,/models,/keys
```
