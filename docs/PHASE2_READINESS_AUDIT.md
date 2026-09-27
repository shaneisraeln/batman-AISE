# BATMAN — Phase 2 Forensic Product-Readiness Audit

**Type:** Read-only forensic audit. No code was modified, published, or deployed.
**Method:** Direct inspection of source, routes, tests, and a live run of the
test suite. Functionality is judged from code + tests, not filenames or docs.

---

## 1. Executive summary

Phase 2 built a **real, working backend** — a multi-tenant FastAPI control +
data plane, a genuinely lightweight SDK, a persistence layer, an
existing-ML-API proxy, and a security engine reused unchanged from Phase 1.
Those parts are largely honest and test-backed.

However, the previous **"Phase 2 — Productization: complete"** claim
**overstates product readiness** in specific, material ways:

1. **The landing page is 100% static.** It contains no signup, login, or
   API-key UI. Its "Protect Your Model" CTA is an in-page anchor; "Open
   Dashboard" is a bare `/app/` link. A visitor cannot create an account from
   the landing page.
2. **The dashboard has a broken feedback path** — `ThreatDetail.jsx` calls
   `api.feedback(...)`, but `api.js` defines no such method. That button throws.
3. **The dashboard was never automatically tested** — there are zero frontend
   tests. It was verified once manually via the Vite proxy.
4. **PostgreSQL is code-complete but not covered by any automated test.** All 84
   backend tests run on SQLite. Postgres was verified once, manually, in Docker.
5. **The SDK is not published** — `batman-ml` returns 404 on PyPI. Only local
   build artifacts exist in `sdk/dist/`.
6. **Nothing is publicly deployed.** The compose stack runs locally; there is no
   live public endpoint, domain, or TLS certificate.
7. **The dashboard and landing are separate containers** — the landing's `/app/`
   link only resolves when the Caddy reverse proxy from `docker-compose.cloud.yml`
   is running; the static landing container alone does not serve the dashboard.

Net: the **engine and backend are real and tested**; the **end-user product
surface (public signup → key → protect) is not wired together for a self-serve
visitor**. See §17 for the explicit launch answer (it is **NO**).

---

## 2. Repository inventory

| Component | Exists | Functional | Tested | Notes |
|---|---|---|---|---|
| Phase 1 detection engine | Yes | Yes | Yes (49) | Unchanged; still green |
| Cloud API (`batman/cloud/app.py`) | Yes | Yes | Yes (10 API + 5 E2E) | control + data plane |
| Control-plane service (`service.py`) | Yes | Yes | Yes (11) | signup/projects/models/keys/upstream |
| Auth / crypto (`crypto.py`) | Yes | Yes | Yes | PBKDF2, HMAC tokens, Fernet |
| Database layer (`batman/db/`) | Yes | Yes (SQLite); Postgres code-complete | SQLite only | No automated PG test |
| API-key management | Yes (backend) | Yes | Yes | UI exists but see §5/§6 |
| Project management | Yes (backend) | Yes | Yes | UI exists (Projects.jsx) |
| Model management | Yes (backend) | Yes | Yes | UI exists (Models.jsx) |
| Upstream config / proxy (`upstream.py`) | Yes | Yes | Yes (unit + E2E) | Fernet-encrypted creds |
| SDK (`sdk/batman_ml`) | Yes | Yes | Yes (13) | thin client; not published |
| Dashboard (`dashboard/`) | Yes | Partially | **No tests** | feedback path broken |
| Landing page (`landing/`) | Yes | Static only | No | no auth/app logic |
| Documentation (`landing/docs/`, `docs/`) | Yes | N/A (static) | N/A | mostly accurate; see §15 |
| Docker (Phase 1 + cloud) | Yes | Builds + runs | Manually verified | not publicly deployed |
| Deployment (Caddy/compose) | Yes | Runs locally | Manually verified | no public host/TLS |
| Tests | Yes | 103 pass | — | backend-heavy; no FE tests |
| Scripts / experiments | Yes | Yes | — | verify_cloud_e2e etc. |

---

## 3. Landing page audit

**Implementation:** `landing/index.html` + `landing/landing.css` + `landing/docs/`.
**No `<script>`, no `<form>`, no `fetch`, no build step** (grep-confirmed).
It is a static brochure served by nginx (`landing/Dockerfile`).

```text
Landing Page CTA Audit
----------------------

Button / Link: "Protect Your Model" (nav + hero)
Destination: #get-started (in-page anchor)
Real route: no — scrolls to a section
Backend integration: none
Authentication required: n/a
Actually functional: NO (navigational only)
Evidence: href="#get-started"; that section only links onward to /app/ and ./docs/

Button / Link: "Read Documentation"
Destination: ./docs/ (static HTML docs)
Real route: yes — static docs page exists
Backend integration: none
Actually functional: YES (static content)
Evidence: href="./docs/"; landing/docs/index.html present

Button / Link: "Open Dashboard" (get-started + footer)
Destination: /app/
Real route: only when the Caddy proxy (docker-compose.cloud.yml) is running,
            which maps /app/* -> dashboard container
Backend integration: indirect (dashboard app, separate container)
Authentication required: yes (dashboard shows a login gate)
Actually functional: PARTIAL — dead link if landing is served standalone;
            resolves only behind the full compose stack
Evidence: href="/app/"; routing lives in deploy/Caddyfile, not the landing container

Sign Up / Login / Get API Key / Create Project / Register Model (on landing)
Destination: DO NOT EXIST on the landing page
Actually functional: NO — there are no such controls in landing/index.html
Evidence: grep for form/script/fetch returns nothing; no auth markup present
```

**Verdict:** The flagged concern is correct. The landing page cannot sign a user
up, log them in, or generate a key. Those actions live only in the separate
dashboard SPA.

---

## 4. Authentication audit

Backend (real, tested):
- User creation — `ControlPlaneService.signup` (dup-email check, email lowercased). ✅
- Password hashing — PBKDF2-HMAC-SHA256, 240k rounds, per-password salt (`crypto.hash_password`). ✅
- Login endpoint — `POST /auth/login` returns a signed token; anti-enumeration verify. ✅
- Token mechanism — stateless HMAC-SHA256 with 7-day expiry (`issue_token`/`verify_token`). ✅
- Auth middleware — `current_user` (Bearer) for control plane; `authenticate_api_key` (x-api-key) for data plane. ✅
- Protected routes — all control-plane + monitoring routes `Depends(current_user)`. ✅
- Invalid credentials rejected — tested (`test_login_wrong_password`, tamper token test). ✅
- Cross-tenant prevention — tested (see §11). ✅

Gaps:
- **No logout endpoint.** The dashboard clears its local token client-side; the
  token remains valid server-side until expiry (no denylist).
- **Password policy is minimal** (length ≥ 8 only).
- **No email verification, no password reset, no refresh tokens.**
- **Frontend flow exists in the dashboard** (`Login.jsx`), **not on the landing
  page.** A public visitor must already know to go to `/app/`.

---

## 5. Project / model management

| Operation | Endpoint | Method | Auth | Persisted | Frontend | Tests |
|---|---|---|---|---|---|---|
| Create project | `/projects` | POST | Bearer | Yes | `Projects.jsx` | Yes |
| List projects | `/projects` | GET | Bearer | Yes | `Projects.jsx` | Yes |
| Register model | `/models` | POST | Bearer | Yes | `Models.jsx` | Yes |
| List models | `/models` | GET | Bearer | Yes | `Models.jsx` | Yes |
| Configure upstream | `/models/{id}/upstream` | PUT | Bearer | Yes (encrypted secret) | `Models.jsx` (UpstreamModal) | Yes |

Backend chain **create account → project → model → upstream** works and is
tested (`test_cloud_service.py`, `test_cloud_api.py`, `test_cloud_e2e.py`).
Frontend components exist for each. **The only missing link is discoverability**:
none of this is reachable from the public landing page — only from the dashboard
SPA, which the landing page does not embed.

---

## 6. API key management

Lifecycle (backend, tested):
- Generation — `secrets.token_urlsafe(32)`, prefix `bm_live_` (`generate_api_key`). ✅
- Entropy — cryptographically secure (`secrets`). ✅
- Hashing — SHA-256; only the hash is stored. ✅
- Constant-time comparison — `hmac.compare_digest` (`verify_key_hash`). ✅
- Storage + association — key bound to user/project/model (`ApiKeyRepository`). ✅
- One-time display — raw key returned only from `POST /keys`. ✅
- Revocation — `DELETE /keys/{id}`, tenant-scoped. ✅
- Revoked-key enforcement — data plane rejects (tested `test_revoked_key_denied`). ✅
- Listing hides hash/secret — tested. ✅

Frontend (dashboard `ApiKeys.jsx`): create (shown once + copy), list, revoke —
all present and wired to the cloud API.

**Caveat:** all of this is behind the dashboard login. There is **no way to get a
key from the landing page**, and no automated frontend test covers the key UI.

---

## 7. Dashboard audit

Routing: an SPA (`App.jsx`) with a login gate; sections switched in-state (no
router). Polls every 4s when authed. Data is fetched from the cloud API with a
Bearer token in `localStorage`. **No hardcoded/seeded/synthetic data in the
dashboard code** — it renders whatever the tenant-scoped API returns.

| Page | Exists | Backend API | Auth | Data source | States | Notes |
|---|---|---|---|---|---|---|
| Login | Yes | /auth/signup,/auth/login | — | real | ok | gate works |
| Overview | Yes | /v1/metrics,/v1/threats | Bearer | real telemetry | has empty states | ok |
| Threats | Yes | /v1/threats | Bearer | real | empty/idle | CTRL- test badge present |
| Threat Detail | Yes | /v1/threats/{id} | Bearer | real | loading/err | **feedback submit BROKEN** |
| Models | Yes | /models,/models/{id}/upstream | Bearer | real | ok | upstream modal |
| Projects | Yes | /projects | Bearer | real | ok | env badges |
| API Keys | Yes | /keys | Bearer | real | ok | one-time reveal |
| Settings | Yes | /auth/me,/v1/health | Bearer | real | ok | quickstart snippet |
| Monitoring | Yes | /v1/metrics,/v1/threats | Bearer | real | idle | charts |
| **Analytics** | **No** | — | — | — | — | nav in brief but no component |
| **Feedback** | **No page** | /v1/feedback (backend only) | — | — | — | no dashboard page; submit path broken |

**Concrete defect:** `ThreatDetail.jsx` calls `api.feedback(requestId, ...)`, but
`dashboard/src/api.js` exports no `feedback` method → runtime `TypeError` when the
analyst clicks a feedback button. Additionally, the cloud `/v1/feedback` requires
`x-api-key` (data-plane auth), which the dashboard does not hold (it uses a Bearer
token), so even if the method existed it would 401.

---

## 8. Cloud API audit

All endpoints in `batman/cloud/app.py` (`create_cloud_app`):

```text
POST /auth/signup     — create user + token   | none    | DB yes | n/a        | tested | dashboard | IMPLEMENTED
POST /auth/login      — token                  | none    | DB yes | n/a        | tested | dashboard | IMPLEMENTED
GET  /auth/me         — current user           | Bearer  | DB yes | self       | tested | dashboard | IMPLEMENTED
POST /projects        — create project         | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
GET  /projects        — list projects          | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
POST /models          — register model         | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
GET  /models          — list models            | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
POST /keys            — create key (once)       | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
GET  /keys            — list keys (no secret)   | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
DELETE /keys/{id}     — revoke key              | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
PUT  /models/{id}/upstream — set upstream       | Bearer  | DB yes | per-user   | tested | dashboard | IMPLEMENTED
GET  /v1/threats      — tenant threats          | Bearer  | DB yes | project_ids| tested | dashboard | IMPLEMENTED
GET  /v1/threats/{id} — incident detail         | Bearer  | DB yes | ownership  | tested | dashboard | IMPLEMENTED
GET  /v1/metrics      — tenant metrics          | Bearer  | DB yes | project_ids| tested | dashboard | IMPLEMENTED
GET  /v1/health       — health                  | none    | n/a    | n/a        | tested | dashboard | IMPLEMENTED
POST /v1/predict      — detect+enforce+proxy     | x-api-key| DB yes | key-scoped | tested | SDK/REST  | IMPLEMENTED
POST /v1/feedback     — analyst feedback         | x-api-key| DB yes | project    | NOT directly tested | none working | PARTIAL (query-param body; no working consumer)
```

Notes:
- `/v1/feedback` takes `request_id`/`label` as **query parameters** (unusual for a
  POST) and is x-api-key-authed; no functional consumer calls it correctly.
- CORS is `allow_origins=["*"]` — permissive for a token-bearing API (see §13).

---

## 9. Existing-ML-API integration audit

Flow **Client → BATMAN → Security engine → configured upstream → prediction** is
**real and verified**:
- Upstream registration/config — `PUT /models/{id}/upstream` persists URL, method,
  path, request/response format, auth type, timeout; secret **Fernet-encrypted**. ✅
- Request/response forwarding — `HTTPModelAdapter` via `adapter_from_config`. ✅
- Encrypted credentials — decrypted transiently in-memory only for headers. ✅
- Upstream failure — `MLServiceError → HTTP 502` (tested). ✅
- Policy enforcement — blocked requests never call upstream (tested). ✅
- Telemetry + project/model association + tenant isolation — recorded and scoped. ✅

Tested by `tests/test_cloud_api.py` (mocked upstream) and `tests/test_cloud_e2e.py`
(real SDK, mocked upstream boundary). Also verified **live** once against the real
`ml-service` in `experiments/verify_cloud_e2e.py`. This is the most
production-credible part of Phase 2.

---

## 10. SDK audit

- Package name: `batman-ml`; import `batman_ml`; version `0.1.0`.
- Dependencies: **only `httpx`** — verified by clean-venv install pulling no
  heavy libs; importing `batman_ml` loads zero heavy modules.
- Public API: `protect()`, `BatmanClient`, `ProtectedModel`, `PredictionResult`,
  full exception hierarchy.
- Auth: `x-api-key` header; key never logged / not in `repr()` (tested).
- Prediction flow: talks to the **hosted API** `/v1/predict` (HTTP) — it does
  **not** run detection locally. Correct architecture.
- Error handling / timeouts / retries: implemented + tested (13 tests).
- Communicates with the hosted BATMAN API: **yes** (confirmed via E2E against the
  in-process app and once live).

---

## 11. PyPI status

- **Not published** — `https://pypi.org/pypi/batman-ml/json` → **404**.
- Build-ready: yes. `sdk/dist/` holds `batman_ml-0.1.0-py3-none-any.whl` + sdist.
- On TestPyPI: **no**.
- `twine check`: passed (recorded previously).
- Clean install: works in a fresh venv (verified previously).
- Publishing remains a manual owner action (documented in `sdk/RELEASE.md`).

---

## 12. Database / multi-tenancy audit

- SQLite: supported, default, fully tested.
- PostgreSQL: **code-complete** (`batman/db/database.py` psycopg path, `?`→`%s`
  translation, `ON CONFLICT` upserts) and **manually verified once in Docker**
  (all 7 tables created; full flow ran). **No automated test uses Postgres** —
  grep for `postgres`/`psycopg` in `tests/` returns nothing.
- Migrations: idempotent `init_schema` + additive column migrations (not a
  formal migration tool like Alembic).
- Tables present: users, projects, models, upstream_configs, api_keys,
  telemetry, feedback. ✅
- Tenant isolation: enforced via `get_owned(id, user_id)` and `project_ids`
  scoping; **tested** —
  - `test_db.py::test_tenant_isolation_projects/_models`
  - `test_cloud_service.py::test_cannot_use_another_users_project`, `test_key_revocation_is_tenant_scoped`
  - `test_cloud_api.py::test_tenant_cannot_see_others_projects`
  - `test_cloud_e2e.py::test_e2e_tenant_isolation_of_telemetry`

User A cannot read/act on User B's projects/models/keys/telemetry — verified.

---

## 13. Deployment audit

Present: `Dockerfile` (Phase 1 gateway), `Dockerfile.cloud` (cloud API),
`docker-compose.yml` (Phase 1 demo), `docker-compose.cloud.yml` (Postgres + API
+ dashboard + landing + Caddy), `deploy/Caddyfile`, `.env.cloud.example`.

- Builds: cloud-api image built; Phase 1 images built previously.
- Runs locally: cloud stack ran (`up postgres cloud-api`) with Postgres Healthy.
- PostgreSQL: yes (compose). Persistent volume: yes.
- Reverse proxy: Caddy config present; routes landing / dashboard /app / API.
- HTTPS: **configured for a real domain but not provisioned** — the Caddyfile
  uses `:80` for local; no domain, no live certificate.
- Health checks: postgres has one; cloud-api relies on `/v1/health` (not wired
  as a compose healthcheck).
- Secrets: via env / `.env` (gitignored); example provided.

### Is BATMAN currently publicly reachable from the Internet?

> **NOT PUBLICLY DEPLOYED.**

`docker compose up` on a laptop is not a public SaaS. There is no domain, no
public host, no TLS certificate, and nothing is currently running.

---

## 14. Security audit (implementation vs. claim)

```text
IMPLEMENTED + TESTED
  - API key hashing (SHA-256) + constant-time verify
  - API key revocation + revoked-key rejection
  - Password hashing (PBKDF2)
  - Tenant isolation (projects/models/keys/telemetry)
  - Upstream credential encryption (Fernet), fail-closed
  - Input validation (validate_request)
  - Rate limiting (data-plane per key/session)
  - Policy authoritative / LLM cannot override / blocked never reaches model

IMPLEMENTED + NOT TESTED
  - Control-plane auth-endpoint throttling (control_limiter) — no explicit test
  - Token expiry (7d) — issue/verify tested, expiry-window not explicitly tested
  - Secret redaction in logging (JSONFormatter) — not asserted by a test

DOCUMENTED ONLY / ASSUMPTION
  - HTTPS/TLS (relies on proxy + a real domain not yet provisioned)
  - Secret-manager storage of BATMAN_SECRET_KEY / ENCRYPTION_KEY

MISSING / WEAK
  - CORS is allow_origins=["*"] on a token-bearing API (should be locked down)
  - No logout / server-side token revocation (denylist)
  - Minimal password policy (length >= 8 only); no lockout/backoff on failed logins beyond the shared limiter
  - No email verification / password reset
  - No CSRF consideration documented (token-in-localStorage model; XSS would expose it)
  - No formal DB migration tooling
```

SQL injection risk: **low** — all queries are parameterized (`?`/`%s`), no string
interpolation of user input into SQL.

---

## 15. Testing audit

Live run at audit time: **84 backend/main pass**, **13 SDK pass**, **6 ML-service
pass** = **103 total, green.** Mapped to functionality:

```text
Feature               Tests   Passing   Coverage confidence
------------------------------------------------------------
Authentication        several   yes     Medium-High (signup/login/token/tamper)
Projects              several   yes     High (CRUD + ownership)
Models                several   yes     High
API Keys              several   yes     High (create/list/revoke/hash-hidden)
Tenant isolation      5+        yes     High
SDK                   13        yes     High (client behavior, errors, no-leak)
Gateway/data plane    several   yes     High (detect+enforce+proxy)
Upstream proxy        2 + E2E   yes     Medium-High (mocked upstream; 1 live run)
Dashboard APIs (FE)   0         —       NONE (no frontend tests at all)
Telemetry             several   yes     High (SQLite)
Security              partial   yes     Medium (key/tenant strong; CORS/logout untested)
Deployment            0 auto    —       NONE automated (manual Docker verification)
PostgreSQL path       0         —       NONE (SQLite only; PG manual once)
```

**Functionality with no meaningful automated test:** the entire dashboard
(frontend), the PostgreSQL backend path, control-plane rate limiting, secret
log-redaction, and deployment.

---

## 16. Documentation audit

- `landing/docs/` and `sdk/README.md`: **accurate** to the implemented API/SDK.
- `docs/PHASE2_SECURITY_AUDIT.md`: mostly accurate, but presents controls without
  flagging the CORS wildcard, missing logout, or the untested Postgres/FE paths.
- **`docs/PHASE2_COMPLETE.md`: OVERSTATED.** Specific corrections:
  - "Professional dashboard … live-verified" — verified manually once; **no tests**
    and a **broken feedback path** remain.
  - The developer-journey diagram implies a self-serve funnel from the website;
    in reality the **landing page has no auth/app** and cannot start that funnel.
  - "verified live on Postgres in Docker" is true but reads as if Postgres is a
    tested, supported production path — it has **no automated coverage**.
  - Landing "Open Dashboard"/`/app/` only works behind the full compose proxy,
    not from the standalone landing container.

---

## 17. Product-readiness matrix

### READY (works end-to-end, tested)
- Phase 1 detection engine + policy enforcement.
- Cloud API control plane (auth, projects, models, keys) on SQLite.
- API-key lifecycle (create/hash/one-time/revoke/reject) — backend.
- Tenant isolation.
- Existing-ML-API proxy with encrypted upstream credentials.
- SDK (`batman-ml`) client behavior — build-ready.

### PARTIALLY READY
- Dashboard: renders real data and manages projects/models/keys, **but** has zero
  tests and a broken feedback action; only reachable at `/app/` behind the proxy.
- PostgreSQL: code-complete, manually verified once, **no automated tests**.
- Deployment: compose stack runs locally; no public host/TLS/healthcheck wiring.
- Security: strong on keys/tenancy; CORS wildcard, no logout, thin password policy.

### NOT READY (claimed-complete but not truly product-ready)
- "Self-serve product" funnel from the public site — the landing page cannot
  sign up / issue keys.
- Dashboard Feedback — broken (`api.feedback` undefined; auth model mismatch).

### DEMO ONLY
- The whole stack as run locally (`docker compose up`) with SQLite or a local
  Postgres — works for a demo/dev, not for public users.
- `experiments/verify_cloud_e2e.py` live run — a controlled local demo.

### MISSING (needed for the planned public product)
- Landing-page auth surface (signup/login) or a real link into a hosted dashboard.
- Dashboard "Analytics" and "Feedback" pages (nav claimed; not implemented).
- Public deployment: domain, TLS certificate, running host.
- PyPI publication of `batman-ml`.
- Automated tests for the frontend, the Postgres path, and deployment.
- Account lifecycle: logout/token-revocation, email verification, password reset.
- Locked-down CORS for the token-bearing API.

---

## 18. Public launch gap analysis

> "If we put the BATMAN landing page on a public domain tomorrow, can a
> completely new developer visit the site, create an account, get an API key,
> connect their ML model/API, and actually protect it without us manually
> touching the backend?"

### Answer: **NO.**

Blockers, in order:
1. **Landing page has no signup/login/app** — it's static; a visitor has nowhere
   to create an account from the marketing site.
2. **Nothing is publicly deployed** — no domain, no TLS, no running host. The
   `/app/` link is dead unless the full compose stack is already running behind
   Caddy.
3. **PyPI package not published** — `pip install batman-ml` would fail (404).
4. **Dashboard is untested and has a broken feedback path** — not launch-safe.
5. **Postgres path unverified by tests** — shipping a public multi-user service
   on SQLite is inadequate; the PG path has no automated coverage.
6. **CORS wildcard + no logout/token revocation** — hardening gaps for a public,
   token-bearing API.
7. **No account recovery** (email verify / password reset) — unacceptable for
   real users.

What *would* work today, manually: an operator runs the compose stack locally,
opens `/app/`, signs up, creates a project/model, sets an upstream, generates a
key, and protects a model via the SDK/REST. That is a **working local product**,
not a **public self-serve SaaS**.

---

## 19. Recommended next steps (not performed — audit only)

To close the gap between "backend works" and "a stranger can self-serve":

1. **Wire the funnel:** make the landing "Protect Your Model"/"Get API Key" CTAs
   route into the real dashboard signup, or embed signup/login on the site.
2. **Fix the dashboard feedback path** (add `api.feedback` + reconcile the
   x-api-key vs Bearer auth model for `/v1/feedback`), or remove the control.
3. **Add frontend tests** and at least one **automated PostgreSQL** test path.
4. **Actually deploy:** provision a domain + TLS, run the compose stack on a
   host, wire a cloud-api healthcheck.
5. **Publish `batman-ml`** (TestPyPI → PyPI) so `pip install` works.
6. **Harden:** lock CORS to known origins, add logout/token revocation, strengthen
   password policy, add email verification + password reset.
7. **Correct `PHASE2_COMPLETE.md`** to distinguish "backend implemented + tested"
   from "public product ready."

---

### Auditor's bottom line

Phase 2 delivered a **genuine, test-backed backend and SDK** and a **credible
existing-ML-API protection path** — that part is real, not vapor. But the
**"complete / productization done"** framing is **overstated**: there is no
public deployment, no self-serve funnel from the landing page, an untested and
partly broken dashboard, an unpublished SDK, and an untested Postgres path. The
honest status is **"working local/dev product with a real backend; not a
publicly launchable SaaS."**
