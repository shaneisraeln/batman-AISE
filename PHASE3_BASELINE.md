# BATMAN Phase 3 — Forensic Baseline

**Stage:** Phase A (read-only). No code was modified while producing this document.
**Date captured:** start of Phase 3.
**Environment:** Windows, PowerShell, Python 3.11.5 (`.venv`), Node 20 / npm (dashboard), Docker 29.6.2.

This is the honest starting state before any Phase 3 changes. Labels used
throughout Phase 3: **VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED / BLOCKED BY
OWNER INFRASTRUCTURE / DEFERRED**.

---

## 1. Test baseline (all commands actually run)

| Suite | Command | Result |
|---|---|---|
| Backend (engine + cloud + funnel) | `.venv\Scripts\python -m pytest -q` | **92 passed, 7 skipped** (VERIFIED) |
| Phase 1 detection engine subset | `pytest tests/test_detection.py test_features.py test_policy.py test_rate_limit.py test_agents.py test_rag.py test_telemetry.py test_validation.py test_integration.py test_http_adapter.py test_auth.py --collect-only` | **49 tests collected** (VERIFIED green as subset) |
| SDK | `cd sdk; ..\.venv\Scripts\python -m pytest -q` | **13 passed** (VERIFIED) |
| ML service | `cd ml-service; ..\.venv\Scripts\python -m pytest -q` | **6 passed** (VERIFIED) |
| Frontend (Vitest + jsdom) | `cd dashboard; npm test` | **18 passed (4 files)** (VERIFIED) |
| PostgreSQL parity | `pytest tests/test_postgres.py` (no `BATMAN_TEST_DATABASE_URL`) | **7 skipped** cleanly; previously **7 passed** against real PG 16 (PARTIALLY — needs env to run) |

The 7 skips in the backend run are the PostgreSQL parity tests, which skip when
`BATMAN_TEST_DATABASE_URL` is unset. Total distinct backend tests collected: 99.

**Phase 1 engine = 49 tests, unchanged and green.**

---

## 2. Repository structure (relevant)

```
batman/            # frozen Phase 1 engine + Phase 2 cloud layer
  cloud/           # app.py (FastAPI), service.py, crypto.py, upstream.py, schemas.py
  db/              # database.py, schema.py, models.py, repositories.py
  detection/ features/ policy/ agents/ rag/ llm/ telemetry/ gateway/
  engine.py adapters.py adapters_http.py config.py
sdk/               # batman-ml client package (httpx-only)
dashboard/         # React + Vite SPA
landing/           # static landing + docs (nginx)
ml-service/        # real reference ML API (breast-cancer model)
deploy/Caddyfile   # reverse proxy, env-driven site address + auto-HTTPS
docker-compose.cloud.yml  Dockerfile.cloud  Dockerfile
docs/              # DEPLOYMENT.md, PHASE2B_COMPLETE.md, PHASE1_VALIDATION.md, etc.
tests/             # 99 backend tests incl. test_e2e_funnel.py, test_postgres.py
```

---

## 3. Backend configuration & security surface (as-is observations)

Read-only findings; each becomes a Phase B action item.

### Authentication (`batman/cloud/crypto.py`, `service.py`, `app.py`)
- Passwords hashed with **PBKDF2-HMAC-SHA256, 240 000 rounds**, 16-byte random
  salt, constant-time verify. No plaintext storage. **(looks solid)**
- Session tokens: **stateless HMAC-SHA256** with 7-day expiry, signed by
  `BATMAN_SECRET_KEY`. Expiry + signature verified on every request.
- **Dev fallback secret**: if `BATMAN_SECRET_KEY` is unset, crypto falls back to
  `"dev-insecure-secret-change-me"`. Acceptable for local dev; **must be
  guaranteed non-default in production** → Phase C action.
- Login runs a dummy `verify_password` even when the user does not exist, to
  reduce user enumeration. **(good)**
- Protected control-plane endpoints require `Authorization: Bearer`. Data plane
  requires `x-api-key`.

### API keys (`batman/gateway/auth.py`, `service.py`)
- Only the **hash** is stored (`hash_key`); raw key returned once at creation.
- Key list endpoint never includes hash/secret.
- Revoked/expired/invalid keys → 401 on the data plane.
- Ownership checked via `get_owned` on project + model before minting.

### CORS (`app.py`)
- Env-driven `BATMAN_CORS_ORIGINS`, **never wildcard**, `allow_credentials=True`,
  explicit methods + headers. Dev default is localhost:5173. **(good; verify
  prod separation in Phase C)**

### Upstream credentials (`crypto.py`, `upstream.py`, `service.py`)
- Encrypted at rest with **Fernet** (fails closed if `cryptography` /
  `BATMAN_ENCRYPTION_KEY` missing). Decrypted only in-memory at call time.
  Never returned in responses. **(good)**

### ⚠ SSRF risk (KNOWN GAP — Phase B/part 4)
- `UpstreamRequest.url` is accepted as a bare string and passed to
  `adapter_from_config` → `HTTPModelAdapter` **with no host/IP validation**.
- A tenant could point an upstream at `http://127.0.0.1`, `http://169.254.169.254`
  (cloud metadata), or private RFC1918 ranges → **Server-Side Request Forgery**.
- **This is the single most important production-blocking security item to fix.**

### Input size (KNOWN GAP — Phase B/part 4)
- `PredictRequest.inputs: Any` — no maximum request-size / dimensionality cap →
  potential resource-exhaustion DoS. Consider an MVP bound.

### Rate limiting (`gateway/rate_limit.py`, `app.py`)
- `control_limiter` (30 rpm / 8 burst) applied to **signup** and **login**.
- `/v1/predict` is rate-limited by the **engine's own per-key limiter**.
- **Not throttled**: `/keys` generation, `/v1/feedback` (both require a valid
  Bearer token, so lower abuse risk). → review in Phase B/part 5.
- Limiter state is **in-memory** → does not coordinate across multiple workers /
  replicas. **Documented MVP limitation**; a shared store (Redis) is future work.

### Email validation
- Signup only checks `"@" in email` (no `EmailStr`). Minor; note for Phase B/C.

---

## 4. Persistence & config

- `batman/db/database.py`: SQLite default; PostgreSQL via `BATMAN_DATABASE_URL`
  (`?`→`%s` param translation). Schema init is additive/idempotent.
- `batman/config.py`: all engine settings from env with safe defaults; validates
  `BATMAN_MODE ∈ {monitor, enforce}`.
- **Config gap**: root `.env.example` documents only Phase 1 engine vars. It is
  **missing** the Phase 2 cloud vars (`BATMAN_DATABASE_URL`, `BATMAN_SECRET_KEY`,
  `BATMAN_ENCRYPTION_KEY`, `BATMAN_CORS_ORIGINS`, `BATMAN_SITE_ADDRESS`,
  `BATMAN_DETECTOR_PATH`). `.env.cloud.example` covers the cloud deploy vars.
  → consolidate in Phase C.

### Secret hygiene (VERIFIED)
- `.gitignore` excludes `.env`, `*.db`, `models/*.joblib`, `datasets/*`.
- `git ls-files` confirms **no `.env`, `.db`, or secret files are tracked**.

---

## 5. Docker / deployment (as-is)

- `Dockerfile.cloud`: installs `.[cloud]` (cryptography + psycopg), then builds
  the reference pools + breast-cancer-calibrated detector **at image build time**
  (`training.prepare` + `training.train --dataset breast_cancer`). So the
  gitignored `.joblib` is **not** required in the repo for deployment — the image
  is self-contained. **(good)**
- `docker-compose.cloud.yml`: postgres (healthcheck) → cloud-api → dashboard →
  landing → caddy; env-driven `BATMAN_SITE_ADDRESS` (auto-HTTPS) + CORS.
  Previously validated with `docker compose config`. **A clean no-cache build is
  NOT YET verified in Phase 3** → Phase D.
- `models/` locally contains `isolation_forest.joblib`,
  `isolation_forest_breast_cancer.joblib`, `demo_model.joblib`.

---

## 6. Dependency audit (npm — dashboard) — BASELINE FINDING

`npm audit` on the dashboard reports **5 vulnerabilities (3 moderate, 1 high, 1
critical)**. Investigated individually:

| Package | Severity | Direct? | Class | Fix | Breaking? |
|---|---|---|---|---|---|
| `vitest` | critical | direct (dev) | test runner — arbitrary file read via Vitest UI server / `@vitest/mocker` | vitest 5.x | **major (2→5)** |
| `vite` | high | direct (dev) | dev-server path traversal / `server.fs.deny` bypass / launch-editor NTLM | vite 8.x | **major (5→8)** |
| `@vitest/mocker` | moderate | transitive | via vitest | vitest 5.x | major |
| `esbuild` | moderate | transitive | dev-server request forgery | vite 8.x | major |
| `vite-node` | moderate | transitive | via vite | vitest 5.x | major |

**Key finding (VERIFIED):** `npm audit --omit=dev` reports **0 vulnerabilities.**
All five are in the **dev/test toolchain (vitest/vite/esbuild)** and affect a
*running dev server / Vitest UI on a developer machine* — **not** the shipped
artifact. The production dashboard is a static `vite build` output served by
`serve`/nginx; none of the vulnerable dev-server code executes in production.
Runtime deps (react, react-dom, recharts) have **0 known vulnerabilities**.

All fixes are `isSemVerMajor: true` (vite 5→8, vitest 2→5). Force-upgrading risks
breaking the test setup. **Decision (to be finalized in Phase B/part 6):** do not
force a breaking upgrade solely to zero the count; document impact honestly and
attempt a safe minor/patch bump only if non-breaking.

---

## 7. Known limitations carried into Phase 3

- **SSRF**: upstream URL unvalidated (highest-priority fix).
- **Predict input size**: unbounded (`inputs: Any`).
- **Rate limiting**: in-memory only (no cross-replica coordination); key-gen and
  feedback endpoints not throttled.
- **npm dev-toolchain vulns**: 5, dev/build-only, fixes are major/breaking.
- **Email verification / password reset**: DEFERRED (post-MVP, from Phase 2B).
- **Public deployment / PyPI publish**: pending owner infrastructure/credentials.
- **Warnings**: Starlette `TestClient`/httpx deprecation warning in the pytest
  run (benign); setuptools license-metadata deprecation on SDK build (benign,
  documented in `sdk/RELEASE.md`).

---

## 8. Phase A conclusion

The MVP is functionally complete and fully test-backed at the code level. Before
it can be called *publicly ready*, Phase 3 must address, in priority order:

1. **SSRF mitigation** on upstream URL (production blocker).
2. Input-size bound on `/v1/predict`.
3. Adversarial tenant-isolation tests (confirm no cross-tenant leakage).
4. Rate-limit review on remaining public endpoints.
5. Logging audit (no secret leakage).
6. Consolidated `.env.example` + explicit dev/staging/prod separation.
7. Clean Docker build validation.
8. Clean-environment external E2E + real-ML validation.
9. SDK finalize + PyPI (stop at owner boundary).
10. Performance measurement.

No Phase 1 engine change is anticipated.
