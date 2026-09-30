# BATMAN — Free Public Deployment Plan

**Goal:** deploy the existing, verified BATMAN MVP publicly at **₹0 infrastructure
cost**, with no core-engine changes.

**Scope note (honest):** the actual deployment requires accounts, browser
authentication, and a database signup that only the repository owner can do.
This plan + the accompanying `render.yaml`, env docs, and
`docs/FREE_PUBLIC_DEPLOYMENT.md` prepare and verify everything that can be done
in-repo; the owner runs the account-gated steps.

---

## Target architecture

```
                         INTERNET
                            │
          ┌─────────────────┴─────────────────┐
          ▼                                   ▼
   ┌──────────────┐   HTTPS (VITE_API_BASE)   ┌──────────────────┐
   │   Vercel     │ ────────────────────────► │   Render (Free)  │
   │ landing +    │                           │  FastAPI cloud   │
   │ dashboard SPA│ ◄──── CORS allow-origin ──│  batman.cloud.app│
   └──────────────┘                           └────────┬─────────┘
                                                        │ SSL
                                                        ▼
                                              ┌──────────────────┐
                                              │  Neon (Free)     │
                                              │  PostgreSQL      │
                                              └──────────────────┘
                                                        │
                                                        ▼
                                          Protected upstream ML API
                                          (customer's model, or the
                                           bundled ml-service for E2E)
```

## Why this split

- **Vercel → frontend.** The dashboard is a static Vite/React build (`vite build`
  → `dist/`) and the landing is static HTML. Vercel's free tier serves static
  sites over global HTTPS with zero config and no card. It cannot run our
  Python API, so the API goes elsewhere.
- **Render (Free web service) → FastAPI.** Render runs a long-lived Python
  process, gives an HTTPS `*.onrender.com` URL, connects to an external DB, and
  needs no credit card. Trade-off: it **sleeps after 15 min idle** (~1 min cold
  start) and has **750 instance-hours/month/workspace** — acceptable for an MVP
  (documented in the free-tier section).
- **Neon (Free) → PostgreSQL, external on purpose.** Render's own free Postgres
  **expires after 30 days** (render.com changelog, 2024-05-20) and is then
  deleted — unusable as a persistent production DB. Neon's free Postgres is
  persistent (no expiry), supports SSL + remote connections, and needs no card.
  See Phase 3 below.
- **No Caddy.** Caddy existed only to reverse-proxy + terminate TLS for the
  self-hosted Docker stack. Vercel and Render both terminate TLS themselves, so
  Caddy is not part of this architecture. (`docker-compose.cloud.yml` + Caddy
  remain valid for a self-hosted VPS deployment; they're just not used here.)

## Phase 3 — Database provider decision (verified against current docs)

| Provider | Free Postgres | Persistent? | SSL | Card needed | Verdict |
|---|---|---|---|---|---|
| **Neon** | 0.5 GB/project, scale-to-zero, 100 CU-h/mo | **Yes (no expiry)** | Yes | No | **CHOSEN** |
| Render free Postgres | 1 GB | **No — deleted after 30 days** | Yes | No | Rejected (not persistent) |
| Supabase | 500 MB, project paused after ~1 week inactivity on free | Yes (but auto-pause) | Yes | No | Viable fallback |

**Decision: Neon.** It is a genuinely free, persistent, SSL-enabled, remotely
reachable Postgres — everything BATMAN needs (schema init, tenant isolation,
telemetry, feedback, encrypted upstream credentials). Neon's 0.5 GB free storage
is ample for MVP telemetry. Supabase is an acceptable fallback but its free
projects auto-pause after ~a week of inactivity; Neon's scale-to-zero resumes in
milliseconds, which pairs better with Render's cold-start behavior.

*(Free-tier facts sourced from neon.com and render.com official docs; content
rephrased for licensing compliance. Verify at deploy time — free tiers change.)*

## Deployment dependencies

- **Owner accounts (free, no card):** GitHub (have it), Neon, Render, Vercel.
- **Local tooling (present):** Node 22, npm 10, git 2.52, Python 3.11, Vercel CLI.
- **Not needed:** Docker for Vercel/Neon; Render CLI (deploy via GitHub +
  `render.yaml`).

## Environment variables (see docs/RENDER_ENVIRONMENT.md for the full table)

- **Render (backend):** `BATMAN_DATABASE_URL` (Neon conn string, secret),
  `BATMAN_SECRET_KEY` (secret), `BATMAN_ENCRYPTION_KEY` (Fernet, secret),
  `BATMAN_CORS_ORIGINS` (the Vercel origin), `BATMAN_ENV=production`,
  `BATMAN_DETECTOR_PATH`, `BATMAN_LLM_PROVIDER=stub`,
  `BATMAN_ALLOW_PRIVATE_UPSTREAM=0`.
- **Vercel (frontend, build-time):** `VITE_API_BASE=https://<render-app>.onrender.com`.

## Database strategy

- Neon Postgres, connection string set **only** as a Render env var (never in
  Git / source / frontend).
- BATMAN auto-creates its schema on boot (`init_schema`, idempotent) — no manual
  migration step.
- The Neon URL must include SSL (Neon connection strings already carry
  `?sslmode=require`); psycopg honors it.

## CORS strategy

- Backend CORS is env-driven (`BATMAN_CORS_ORIGINS`), **never `*`**.
- Set it to the exact Vercel production origin, e.g.
  `https://batman-dashboard.vercel.app`. Add preview origins explicitly only if
  needed.

## Deployment order

1. **Neon**: create project → copy connection string.
2. **GitHub**: push repo (done) so Render can build from it.
3. **Render**: create Web Service from repo (`render.yaml`), set env vars
   (incl. Neon URL), deploy → get `*.onrender.com` URL.
4. **Verify backend**: `curl https://<render>/v1/health`, signup/login.
5. **Vercel**: deploy dashboard with `VITE_API_BASE=https://<render>` → get
   `*.vercel.app` URL.
6. **CORS**: set `BATMAN_CORS_ORIGINS` on Render to the Vercel URL → redeploy.
7. **Public E2E** through the browser + SDK.

## Verification

- Backend: `/v1/health` returns `{"status":"ok",...,"detector_ready":true}`;
  signup→login→`/auth/me` round-trip proves Postgres connectivity.
- Frontend: landing loads, `#/signup`→dashboard, network tab shows calls to the
  Render origin (not localhost).
- Full funnel: signup → project → model → key → predict → attack → telemetry →
  feedback → revoke (401) → logout.

## Rollback

- **Frontend:** `vercel rollback` (or redeploy a previous commit); Vercel keeps
  immutable previous deployments.
- **Backend:** in Render, "Rollback" to a prior deploy, or push a revert commit
  (auto-deploys). Config-as-code means `render.yaml` changes are reversible via
  git revert.
- **Data:** Neon has branching/point-in-time on paid tiers; on free, treat data
  as recreatable MVP data (no critical data to lose).

## Free-tier limitations (honest)

- **Render web service sleeps after 15 min idle**; first request after sleep
  takes ~1 min (cold start). Acceptable for MVP; documented for reviewers.
- **Render: 750 instance-hours/month/workspace** — one always-consuming service
  ≈ 720–744 h/month, so a single free service fits; a second free service could
  exhaust hours.
- **Neon free: 0.5 GB storage/project, 100 CU-hours/month, scale-to-zero.**
  Fine for MVP telemetry volume.
- **No custom domain purchased** — use `*.vercel.app` + `*.onrender.com`.

## Owner actions (cannot be automated here)

- Create Neon / Render / Vercel accounts (free, no card).
- Complete `vercel login` browser auth.
- Create the Neon DB and copy the connection string into Render env.
- Connect the GitHub repo to Render and trigger the first deploy.
- Set `BATMAN_CORS_ORIGINS` to the real Vercel URL after the frontend is live.

All exact commands are in **docs/FREE_PUBLIC_DEPLOYMENT.md**.
