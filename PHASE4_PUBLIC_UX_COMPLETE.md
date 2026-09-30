# Phase 4 (Part 2) — Public Landing → Application UX: COMPLETE

This pass connects and polishes the already-built pieces (landing, auth,
onboarding, dashboard) into **one coherent public product** that a developer who
has never seen the repo can use end-to-end without knowing any internal route.

No Phase 1 engine changes. No new features. No auth/onboarding rebuild. This was
an **integration + polish** pass, plus the deployment wiring that makes the whole
thing hold together on Vercel.

---

## 1. Before → After

**Before.** The landing page (`landing/`) and the dashboard SPA (`dashboard/`)
were two separate artifacts. The landing CTAs use the absolute path
`/app/#/signup` and `/app/#/login`. Deployed as two separate Vercel projects
(two `*.vercel.app` domains), those CTAs would be **dead links (404)** on the
landing domain — the "disconnected experience" this task targeted. The app-side
journey (signup → onboarding → dashboard) already worked; the true gap was the
**join** between the marketing site and the app on a real host.

**After.** A single-origin build ships landing, docs, and the dashboard as **one
deployment**:

- `/` → landing (`index.html`, `landing.css`)
- `/docs/` → docs (static)
- `/app/` → the Vite dashboard, built with base `/app/`

Every landing CTA is now a live same-origin link into the real app. Plus small
UX joins: returning users with no project are routed to onboarding (not an empty
dashboard), and the auth screen has a "← Back to site" link.

---

## 2. Changes made

1. **Single-origin combined build** — `scripts/build_site.mjs` + root
   `vercel.json`.
   - `build_site.mjs` builds the dashboard with `VITE_BASE=/app/`, then
     assembles `public_site/` = `{ index.html + landing.css (landing), docs/,
     app/ (dashboard dist) }`.
   - `vercel.json` uses that build and adds SPA rewrites so `/app` and
     `/app/...` resolve to the dashboard shell. Because the app uses **hash
     routing**, `#/...` never reaches the server — only the `/app/` base needs to
     resolve, so refresh and deep links are safe.
2. **Login → onboarding when the account has no project.** `App.jsx` `onAuthed`
   is now async: on login it calls `api.projects()` and routes to `onboard` if
   there are zero projects, else `app`. Fresh signups always → onboarding.
   Backend-supported; no new endpoints.
3. **"← Back to site" link** on the auth screen (`Login.jsx` + `.auth-back` in
   `styles.css`) and the sidebar brand is now a link to `/` — users can move
   between the marketing site and the app.
4. **4 new frontend tests** for the public-journey wiring (see §6).
5. **Docs** — `docs/PUBLIC_UX_AUDIT.md` (Step 1 forensic audit),
   `docs/PUBLIC_USER_JOURNEY.md` (the end-to-end path), and
   `docs/FREE_PUBLIC_DEPLOYMENT.md` updated (§8–10) for the single-origin Vercel
   model.

Files touched: `dashboard/src/App.jsx`, `dashboard/src/components/Login.jsx`,
`dashboard/src/styles.css`, `dashboard/src/test/App.test.jsx`, `.gitignore`
(+`public_site/`), `docs/FREE_PUBLIC_DEPLOYMENT.md`. New: `scripts/build_site.mjs`,
`vercel.json`, `docs/PUBLIC_UX_AUDIT.md`, `docs/PUBLIC_USER_JOURNEY.md`, this file.

---

## 3. Authentication flow

- Bearer token in `localStorage["batman_token"]` (`api.js`
  `getToken/setToken/isAuthed`).
- Signup `POST /auth/signup`, login `POST /auth/login`; `/auth/me` validates.
- `VITE_API_BASE` (build-time) prefixes every API call — empty in dev (Vite
  proxy), the absolute Render URL in production.
- Any 401 → `api.js` throws `"unauthorized"` → `App` clears the token → back to
  Login. Client gate + independent **backend** rejection, so protection is real.

## 4. Onboarding

4 real steps — project → model → API key (shown once, copy button) → integrate
(SDK + REST snippets using the just-created key). Auto-skips ahead if the account
already has data. Both "skip for now" and "Enter the Batcave" reach the app.

## 5. Routing — public vs protected

- **Public:** `/` (landing), `/docs/`.
- **App shell:** `/app/` is served to everyone, but every dashboard **view** is
  gated client-side on the token, and the backend rejects any
  unauthenticated/revoked-key request. A logged-out visitor at `/app/` sees only
  the login/signup screen.
- **Hash routing** (`router.js`: `login | signup | onboard | app`) — chosen so
  the static landing can deep-link into SPA screens with no server routing, and
  so refresh never 404s.

## 6. Vercel considerations (VERIFIED)

- **Single origin** — one Vercel project built from the repo root via
  `scripts/build_site.mjs`; landing, docs, and app share a domain, so landing
  CTAs (`/app/#/signup`, `/app/#/login`) are live links, not 404s.
- **Refresh / deep links survive** — hash fragments aren't sent to the server;
  the SPA rewrite resolves `/app/...` to the dashboard shell. VERIFIED locally:
  `/`, `/app/`, `/docs/` all return 200 when serving `public_site/`.
- **API base** — set `VITE_API_BASE` to the Render backend URL at build time;
  VERIFIED it is baked into the bundle. (Prompt guessed `VITE_API_URL`; the real
  env var in this codebase is **`VITE_API_BASE`**.)

---

## 7. Tests & verification

**Frontend** — `dashboard/` `npm test` → **22 passed** (was 18; +4 this pass in
`src/test/App.test.jsx`):
1. signup → routes to onboarding,
2. login with no projects → onboarding,
3. login with projects → dashboard,
4. "← Back to site" link has `href="/"`.

> Gotcha: `VITE_API_BASE` / `VITE_BASE` leak into Vitest and bake an absolute URL
> into the test bundle (mocks 404). Clear them before testing:
> `$env:VITE_API_BASE=$null; $env:VITE_BASE=$null` then `npm test`.

**Backend** — `.venv\Scripts\python -m pytest -q` → **150 passed, 7 skipped**
(unchanged; nothing backend was touched). Phase 1 engine subset (49 tests) green
and untouched.

**Single-origin build (VERIFIED).** `node scripts/build_site.mjs` (with
`VITE_API_BASE` set) → `public_site/` = `{ index.html, landing.css, docs/, app/ }`;
app assets reference `/app/assets`; API base baked into the bundle. Served via
`npx serve public_site -l 4321`: `/`=200, `/app/`=200, `/docs/`=200.

**Clean-browser end-to-end (VERIFIED — RESULT: PASS).** Built `public_site` with
`VITE_API_BASE=http://localhost:8100`; started the real ml-service (:9000) and
the cloud API (:8100, `BATMAN_CORS_ORIGINS=http://localhost:4321`) plus the
static site (:4321), then drove the funnel as a fresh browser would:
- CORS preflight → `access-control-allow-origin: http://localhost:4321`
- signup 200 → `/auth/me` 200 → create project / model / upstream / key
- `POST /v1/predict` 200 → action `LOG`, prediction `[0]` from the **real model**
- `GET /v1/metrics` → `total_requests=1`
- revoked-key reuse → 401; no-token → 401

All three servers were stopped and temp artifacts (test DB, temp script) cleaned.

---

## 8. Definition of Done

| # | Item | Status |
|---|------|--------|
| 1 | Public UX audit documented | ✅ VERIFIED — `docs/PUBLIC_UX_AUDIT.md` |
| 2 | Landing is a real entry point; CTAs live | ✅ VERIFIED — single-origin build |
| 3 | "Get Started" → real signup | ✅ VERIFIED — `/app/#/signup` |
| 4 | "Log in" → real login | ✅ VERIFIED — `/app/#/login` |
| 5 | No dead links / no manual routes | ✅ VERIFIED — same-origin, 200s |
| 6 | Fresh signup → onboarding | ✅ VERIFIED — test |
| 7 | Returning login w/ no project → onboarding | ✅ VERIFIED — test |
| 8 | Returning login w/ project → dashboard | ✅ VERIFIED — test |
| 9 | Back-to-site / home affordances | ✅ VERIFIED — link href="/" + test |
| 10 | No fabricated metrics/keys | ✅ VERIFIED — real backend, honest empty states |
| 11 | Vercel routing (refresh, deep links) | ✅ VERIFIED — hash routing + rewrite, 200s |
| 12 | `VITE_API_BASE` baked at build | ✅ VERIFIED — bundle inspection |
| 13 | Frontend tests added | ✅ VERIFIED — 22 passed |
| 14 | Backend tests still green | ✅ VERIFIED — 150 passed / 7 skipped |
| 15 | Clean-browser E2E | ✅ VERIFIED — RESULT: PASS |
| 16 | Public user journey documented | ✅ VERIFIED — `docs/PUBLIC_USER_JOURNEY.md` |
| 17 | Actual Vercel/Render/Neon deploy | ⛔ BLOCKED-HUMAN-ACTION (owner accounts + browser auth) |

---

## 9. Remaining limitations (honest)

- **Deployment is owner-gated.** The actual Vercel + Render + Neon deploy needs
  owner accounts and `vercel login` browser auth. Not attempted, not faked.
  Everything the repo can control (build, config, routing, env contract) is done
  and verified; `docs/FREE_PUBLIC_DEPLOYMENT.md` has the step-by-step.
- **Render free tier cold start.** The free backend sleeps when idle; the first
  request after sleep is slow (~30–60s). Documented for users.
- **Not built (deliberately, per scope):** email verification, password reset,
  billing, teams, OAuth/SSO, RBAC. Deferred post-MVP.
- **Logged-in landing visitor** still sees marketing CTAs (no "Dashboard"
  shortcut on the static page). Minor; the app itself lives under `/app/`.
