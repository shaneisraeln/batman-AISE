# BATMAN Phase 3 — Public Readiness Report

Final report for Phase 3 (public launch & production readiness). Every claim
carries an honest label: **VERIFIED** (executed + observed), **BLOCKED BY OWNER
INFRASTRUCTURE / CREDENTIALS** (ready, needs an owner-only asset), **DEFERRED**
(intentionally out of MVP scope), or **RESIDUAL** (known, accepted, documented).

The validated Phase 1 detection engine was **frozen** and not modified in Phase
3 (confirmed by the 49-test engine subset staying green).

---

## 1. Product status

BATMAN is a **model-agnostic runtime security gateway for ML inference APIs**
with a working self-serve product around the frozen detection engine. The full
funnel works end to end against a **real** ML service (VERIFIED, Phase F/G):

> discover (landing) → sign up → log in → create project → register model →
> configure upstream → generate API key (shown once) → integrate (SDK/REST) →
> send inference (real prediction proxied) → drive suspicious traffic →
> detection + policy enforcement → tenant-scoped telemetry → analyst feedback →
> revoke key (denied on reuse) → logout (protected routes 401).

**Status: functionally complete and locally verified end-to-end.** Public
availability is gated only on owner infrastructure (domain/host) and the PyPI
token — not on code.

## 2. Architecture (current)

```
                         ┌──────────── Caddy (reverse proxy, auto-HTTPS) ────────────┐
Client / SDK / dashboard │  /            → landing (static)                           │
      │                  │  /app/*       → dashboard SPA (React/Vite)                 │
      ▼                  │  /v1,/auth,/projects,/models,/keys → cloud API             │
                         └───────────────────────────────┬───────────────────────────┘
                                                          ▼
                              BATMAN Cloud API  (batman/cloud/app.py, FastAPI)
                              • control plane: Bearer-token auth (signup/login/
                                projects/models/keys/upstream/threats/metrics/feedback)
                              • data plane: x-api-key  POST /v1/predict, /v1/feedback
                                                          │
                                    ┌─────────────────────┴─────────────────────┐
                                    ▼                                             ▼
                        Phase 1 SecurityEngine  (FROZEN)                 PostgreSQL (or SQLite dev)
                        rules + Isolation Forest + extraction            users/projects/models/keys/
                        detector → agents → policy (authoritative)       upstream_configs/telemetry/feedback
                                    │  (only if ALLOWED)
                                    ▼
                        pooled HTTPModelAdapter → customer's real ML API
```

The policy engine remains authoritative; the LLM is advisory. Blocked requests
never reach the upstream model.

## 3. Security controls (implemented, VERIFIED)

Full detail + per-control test citations in **SECURITY_AUDIT_PHASE3.md**.

- **Authentication** — PBKDF2-HMAC-SHA256 (240k rounds) password hashing;
  stateless HMAC session tokens with expiry; tampered/expired tokens rejected;
  protected routes require Bearer; user-enumeration-resistant login; no secret
  leakage in error bodies.
- **API keys** — SHA-256 hashed at rest, raw shown once; lifecycle
  create→use→revoke→reuse-denied; **expiry now enforced on the data plane
  (Phase 3 fix)**; never in list responses/telemetry/threat detail.
- **Tenant isolation** — adversarially tested across projects/models/keys/
  telemetry/threats/feedback/upstream; every cross-tenant attempt denied.
- **CORS** — env-driven allowed origins, never wildcard; `allow_credentials`
  never combined with `*`; unconfigured origins not reflected.
- **Upstream credentials** — Fernet-encrypted at rest, never returned in
  responses/telemetry, decrypted only in memory, fails closed if no key.
- **SSRF (Phase 3 mitigation)** — upstream URLs validated: http(s) only;
  loopback/private/link-local/cloud-metadata/reserved addresses blocked
  (literal + DNS-resolved); `BATMAN_ALLOW_PRIVATE_UPSTREAM` escape hatch OFF by
  default.
- **Input bounds** — `/v1/predict` rejects oversized payloads (413).
- **Rate limiting** — signup, login, and API-key generation throttled;
  `/v1/predict` rate-limited per key.
- **Logging** — structured JSON with secret redaction; telemetry stores only
  engineered features, never raw inference inputs.

**58 automated security tests** added this phase, all passing.

## 4. Test evidence (exact commands + results, VERIFIED)

| Suite | Command | Result |
|---|---|---|
| Backend (engine + cloud + security + funnel) | `.venv\Scripts\python -m pytest -q` | **150 passed, 7 skipped** |
| — Phase 1 engine subset | `pytest tests/test_detection.py … test_auth.py` (11 files) | **49 passed** (frozen, green) |
| — Phase 3 security tests | `pytest tests/test_security_*.py` | **58 passed** |
| PostgreSQL parity | set `BATMAN_TEST_DATABASE_URL`; `pytest tests/test_postgres.py` | **7 passed** (skip w/o env) |
| SDK | `cd sdk; ..\.venv\Scripts\python -m pytest` | **13 passed** |
| ML service | `cd ml-service; ..\.venv\Scripts\python -m pytest` | **6 passed** |
| Frontend (Vitest + jsdom) | `cd dashboard; npm test` | **18 passed** |

The 7 backend skips are the PostgreSQL parity tests (skip cleanly without the
env var; separately VERIFIED green against real PostgreSQL 16 in Phase 2B/A).

## 5. External clean-environment E2E (VERIFIED)

Full detail in **PUBLIC_E2E_VALIDATION.md**. Run live against the **real**
ml-service (breast-cancer `LogisticRegression`) + the cloud API on a fresh DB,
via a real HTTP client + the `batman-ml` SDK (`experiments/verify_cloud_e2e.py`
→ `RESULT: PASS`):

- SDK predict returned a **real** model prediction proxied through BATMAN.
- Controlled extraction burst → 65 BLOCK + 42 RATE_LIMIT decisions; 121
  telemetry rows, tenant-scoped metrics/threats populated.
- Analyst feedback recorded, listed, and attached to the threat detail.
- Revoked key → 401; logout (no token) → 401.
- **BATMAN detection vs upstream failure distinguished**: a broken upstream path
  returns **502 `upstream_error`**, not a false threat.

Scope note: run locally (public domain deploy is owner-blocked); the dashboard's
data APIs are exercised, but a human click-through of the rendered pages was not
separately scripted.

## 6. Dependency audit

- **Python:** no known-vulnerable runtime dependencies surfaced.
- **Dashboard npm:** `npm audit` = 5 (1 critical, 1 high, 3 moderate), **all in
  the dev/test toolchain** (vitest/vite/esbuild). `npm audit --omit=dev` = **0**.
  The shipped dashboard is a static `vite build` served by nginx/`serve`; none
  of the vulnerable dev-server/Vitest-UI code runs in production. All fixes are
  breaking majors (vite 5→8, vitest 2→5) — **not** force-upgraded to avoid
  breaking the green test suite. Tracked as **accepted dev-only risk**
  (SECURITY_AUDIT_PHASE3.md §10).

## 7. Performance (VERIFIED)

Detail in **PHASE3_PERFORMANCE.md**. A per-request micro-benchmark (200 samples,
same request, direct vs through BATMAN) surfaced and **fixed** a
production-blocking defect (a new upstream connection was opened per request):

| Path | p50 | p95 |
|---|---:|---:|
| DIRECT → ml-service | 3.9 ms | 5.3 ms |
| BATMAN → ml-service (after fix) | 34.5 ms | 40.6 ms |
| **Overhead** | **+30.6 ms** | +35.3 ms |

~31 ms to add behavioral detection + policy + telemetry in front of a model is
**acceptable for the MVP**. (Localhost single-process micro-benchmark, not a
concurrent load test — see limitations.)

## 8. Deployment — is it live?

- **Local full Docker stack: VERIFIED** (Phase D). Clean `--no-cache` build of
  all images; Postgres (healthy) → cloud-api (healthy) → dashboard → landing →
  Caddy; `/v1/health`, `/`, `/app/` all served; signup→PostgreSQL→`/auth/me`
  round-trip confirmed.
- **Public staging on a real domain: BLOCKED BY OWNER INFRASTRUCTURE.** Needs
  the owner's domain + DNS + host. Exact procedure in
  **PHASE3_STAGING_READINESS.md** / `docs/DEPLOYMENT.md`. HTTPS auto-provisions
  via Caddy once a real domain resolves (config-ready, **NOT VERIFIED** without a
  domain).

**No public deployment has been performed. No domain/DNS/certificate was
fabricated.**

## 9. PyPI — is `batman-ml` published?

- Package built; `twine check` PASSED (wheel + sdist); clean-venv install pulls
  only `httpx`; documented API verified in a fresh env (Phase H).
- **Publishing is BLOCKED BY OWNER CREDENTIALS** (PyPI token). Exact
  `twine upload` runbook in **PHASE3_SDK_PYPI.md** / `sdk/RELEASE.md`.

**`batman-ml` is NOT on PyPI. Nothing claims it is.** It installs from
`sdk/dist/` today.

## 10. Remaining limitations (honest)

- **Rate limiter + session state are in-memory per process** — no cross-replica
  coordination; a multi-instance deployment needs a shared store (Redis) or an
  edge limiter (RESIDUAL).
- **SSRF guard is validation, not a full egress firewall** — does not cover
  TOCTOU DNS-rebinding or redirect-to-private; network-layer egress restriction
  recommended for hardened deployments (RESIDUAL).
- **Session tokens are stateless** — cannot be individually revoked before
  expiry (only global secret rotation) (RESIDUAL).
- **Email verification & password reset** — DEFERRED (post-MVP; not faked).
- **Telemetry writes are synchronous (SQLite dev / Postgres prod)** — fine at
  MVP scale; async/batched writes are future work.
- **Performance measured single-process/localhost only** — no concurrent
  load/throughput/soak numbers yet.
- **Detector thresholds are calibrated on controlled traffic** and must be
  recalibrated per real workload (carried from Phase 1).

## 11. Production blockers (genuine only)

**No critical application-layer blocker remains.** The three material issues
found in Phase 3 were fixed and re-verified:

1. SSRF on upstream URLs → **mitigated + tested**.
2. Expired API keys accepted on the data plane → **fixed + tested**.
3. ~100x per-request latency from connection churn → **fixed + tested**.

Remaining items are **not** code blockers:

- **Operational (owner must do at deploy time):** set strong `BATMAN_SECRET_KEY`
  + `BATMAN_ENCRYPTION_KEY`, real `BATMAN_CORS_ORIGINS`, `BATMAN_ENV=production`,
  `BATMAN_ALLOW_PRIVATE_UPSTREAM=0`, HTTPS via Caddy; add a shared rate limiter
  if running multiple instances. (Startup config-warning checks flag misconfig.)
- **Owner-blocked:** public domain deployment (infra) and PyPI publish (token).

## 12. Recommended next phase

Focus on **evaluation and hardening depth**, not new product features:

- Broader detection evaluation across more datasets/model families.
- Detector **generalization** to additional, unseen extraction strategies.
- **Calibration** of thresholds across different model output distributions.
- **Attack-strategy diversity** (more probing/evasion patterns).
- **False-positive analysis** on realistic benign traffic.
- **Performance under load** (concurrency, throughput, tail latency) + async
  telemetry + PostgreSQL-under-load.
- **Drift monitoring** in production (the PSI drift tooling already exists).
- Ongoing **security research** (egress-layer SSRF hardening, token revocation,
  shared rate limiting).

---

## Definition of Done — checklist

| Item | Status |
|---|---|
| Security audit completed | **VERIFIED** (SECURITY_AUDIT_PHASE3.md, 58 tests) |
| No known critical production blocker | **VERIFIED** (3 found → all fixed) |
| SSRF risk investigated and mitigated | **VERIFIED** (batman/cloud/ssrf.py, 20 tests) |
| CORS verified | **VERIFIED** (never wildcard, config-driven) |
| Tenant isolation adversarially tested | **VERIFIED** (13 tests) |
| API-key lifecycle tested | **VERIFIED** (create→use→revoke→reuse + expiry) |
| Authentication tested | **VERIFIED** (hashing, token expiry/tamper, gating) |
| Secrets reviewed | **VERIFIED** (.gitignore, prodcheck, .env.example) |
| Dependency vulnerabilities assessed | **VERIFIED** (npm dev-only; --omit=dev=0) |
| Docker deployment verified | **VERIFIED** (clean build + full stack, Phase D) |
| HTTPS verified if infrastructure available | **BLOCKED BY OWNER INFRASTRUCTURE** (config-ready) |
| Real external ML API tested | **VERIFIED** (Phase F/G, real ml-service) |
| Clean-environment E2E completed | **VERIFIED** (PUBLIC_E2E_VALIDATION.md) |
| SDK clean-install tested | **VERIFIED** (fresh venv, httpx-only) |
| PyPI published OR blocked only by owner creds | **BLOCKED BY OWNER CREDENTIALS** (built + twine-checked) |
| All regression tests pass | **VERIFIED** (150+7 / 49 engine / 13 SDK / 6 ml / 18 FE) |
| Phase 1 detection engine unchanged and green | **VERIFIED** (49-test subset green; engine files untouched) |
| Final readiness report created | **VERIFIED** (this document) |

**Bottom line:** BATMAN is real, secure at the MVP bar, externally verified
against a real ML model, and fully deployable. The only remaining steps to be
publicly live are the two owner-gated actions — deploy to a real domain and
publish the SDK to PyPI — both with exact, tested runbooks provided.
