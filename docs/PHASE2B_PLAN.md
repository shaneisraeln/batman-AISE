# BATMAN — Phase 2B Plan (Product Completion)

**Goal:** a new developer can visit the site → sign up → log in → create a
project → register a model → generate a key → integrate (SDK/gateway) → send
real inference → see real telemetry, with no manual backend intervention.

**Non-negotiable:** the validated Phase 1 detection engine is not touched.
Existing tests stay green.

---

## Reuse map (gap → existing code to build on)

| Audit gap | Existing reusable code | Action |
|---|---|---|
| 1–3 Landing static, no onboarding | `landing/index.html`; dashboard `Login.jsx` already calls real backend | Point CTAs at `/app/#/signup`; add hash routing + onboarding to SPA |
| 4–5 Dashboard feedback broken | `ThreatDetail.jsx` calls `api.feedback` (missing); backend `record_feedback`, `FeedbackRepository` exist | Add Bearer `/v1/feedback` + `api.feedback`; tenant-scoped |
| 6 Analytics page missing | `/v1/metrics`, `/v1/threats` exist; `Overview.jsx`/`Monitoring.jsx` patterns | New `Analytics.jsx` from real data |
| 7 Feedback page missing | `FeedbackRepository.get`; need list-by-user | New `GET /v1/feedback` + `Feedback.jsx` |
| 8 Logout/token revocation | `api.logout()` clears local token | Client logout works; document stateless-token limitation (no server denylist in MVP) |
| 9–10 Email verify / reset | — | **Deferred to post-MVP, documented honestly** (no fake claims) |
| 10 CORS wildcard | `CORSMiddleware(allow_origins=["*"])` | Env-driven `BATMAN_CORS_ORIGINS` |
| 11 PG not auto-tested | `batman/db/database.py` PG path works | Guarded pytest via `BATMAN_TEST_DATABASE_URL` |
| 12 SDK not published | `sdk/` build-ready | Build + check; stop at publish boundary |
| 13–14 Not deployed | `docker-compose.cloud.yml`, `deploy/Caddyfile` | Finalize staging runbook; stop at real-domain boundary |
| 15 Onboarding incomplete | control-plane endpoints all exist | Onboarding wizard ties them together |

---

## Backend changes (`batman/`)

- `cloud/app.py`
  - Replace wildcard CORS with `BATMAN_CORS_ORIGINS` (comma-separated; default
    `http://localhost:5173,http://127.0.0.1:5173`).
  - Add **Bearer-authed** `POST /v1/feedback` (JSON body) that verifies the
    threat's project belongs to the caller (tenant isolation), then records it.
    Keep the existing x-api-key `/v1/feedback` for SDK/data-plane callers but
    move it to `/v1/data/feedback` to avoid the auth-model clash (or keep both
    with distinct dependencies). **Decision:** dashboard uses Bearer
    `POST /v1/feedback`; SDK path stays available but is not required for MVP.
  - Add **Bearer-authed** `GET /v1/feedback` — tenant-scoped analyst feedback list.
- `cloud/service.py` — add `record_feedback_for_user(user_id, request_id, label, note)`
  (checks the telemetry row's project is owned by the user) and
  `list_feedback_for_user(user_id)`.
- `db/repositories.py` — `FeedbackRepository.list_for_projects(project_ids)`
  (join feedback ↔ telemetry.project_id) for tenant scoping.
- No schema change required (feedback + telemetry tables already exist; scope via
  telemetry.project_id).

## Frontend changes (`dashboard/`)

- `src/router.js` (new) — tiny hash router: `#/login`, `#/signup`, `#/onboard`,
  `#/app` (default). No new dependency.
- `src/api.js` — add `feedback(request_id,label,note)`, `listFeedback()`; keep
  logout client-side.
- `src/components/`
  - `Onboarding.jsx` (new) — guided project → model → (optional upstream) → key.
  - `Analytics.jsx` (new) — real metrics + threat-category breakdown, honest empty state.
  - `Feedback.jsx` (new) — real feedback list, tenant-scoped.
  - `ThreatDetail.jsx` — fix feedback call to the Bearer endpoint.
  - `App.jsx` — add Analytics + Feedback to nav; route signup/login/onboard.
- `landing/index.html` — CTAs: "Get Started" → `/app/#/signup`, add "Login" →
  `/app/#/login`; keep design + honest positioning.

## Deployment changes

- `docker-compose.cloud.yml` / `deploy/Caddyfile` already present; add
  `BATMAN_CORS_ORIGINS` env; document staging domain placeholders + HTTPS.
- Provide a runbook; **stop** at real-domain provisioning + PyPI publish
  (require owner infra/credentials).

## Security implications

- CORS locked to configured origins (prevents arbitrary cross-origin token use).
- Feedback endpoints enforce tenant ownership of the underlying threat row.
- Stateless tokens: MVP has no server-side revocation/denylist — **documented**,
  not hidden. Logout clears the client token; consider a denylist post-MVP.
- Email verification / password reset: **explicitly post-MVP**, documented.

## Test plan

- Backend: new tests for CORS config, Bearer feedback (success + cross-tenant
  denial), feedback listing tenant scoping. Keep all existing green.
- PostgreSQL: guarded suite (`BATMAN_TEST_DATABASE_URL`) covering auth/projects/
  models/keys/telemetry/tenant isolation; skips cleanly when unset.
- Frontend: Vitest + jsdom for login, gate, project/model/key create, key
  one-time display, revoke, threat list/detail, feedback submit, analytics
  render, logout (fetch mocked).
- E2E: full-funnel pytest (signup→…→revoke→401→logout) + live script incl. feedback.

## Order of execution

Tasks #2 → #11 as listed. Run tests after each stage. No completion claims
without evidence.
