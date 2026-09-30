# BATMAN — Public UX Audit (Step 1)

Forensic findings on the current landing → app → onboarding → dashboard
experience, before any changes. Read-only inspection.

## 1. How the landing page is served
Static files in `landing/`: `index.html` + `landing.css` + `docs/` (docs is its
own static `index.html` + `docs.css`). No build step. Served by nginx in the
Docker stack; intended to be served at `/` in production.

## 2–4. How signup / login / `/app` are routed
The landing is **separate** from the dashboard app. Landing anchor CTAs point to
**absolute** paths:
- **Get Started / Protect Your Model / Create Free Account** → `/app/#/signup`
- **Log in / Dashboard** → `/app/#/login`
- **Documentation** → `./docs/` (relative)

The dashboard (`dashboard/`, Vite+React) is the `/app/` SPA. Inside it, the hash
after `/app/#/...` selects the screen. So the design intent is a **single origin**
where `/` = landing, `/app/` = dashboard, `/docs/` = docs.

## 5. Hash vs history routing
**Hash routing** (`dashboard/src/router.js`): routes are the string after `#/`
(`login`, `signup`, `onboard`, `app`). This is deliberate so the static landing
can deep-link into SPA screens with no server-side routing, and so page refresh
never 404s on a sub-route (the hash isn't sent to the server).

## 6. Authentication state
Bearer token in `localStorage` under `batman_token` (`api.js`
`getToken/setToken/isAuthed`). `VITE_API_BASE` (build-time) prefixes every API
call; empty in dev (Vite proxy), absolute Render URL in production.

## 7. Protected routes
`App.jsx` gates on `authed = isAuthed()`. If not authed, **only** the `Login`
screen renders (signup or login tab from the hash) — no dashboard view is
reachable. On a 401 from any call, `api.js` throws `"unauthorized"`, `App`
clears auth and drops back to Login. This is a client-side guard; the **backend**
independently rejects every unauthenticated/again-401 request, so protection is
real, not cosmetic.

## 8. After login
`Login` calls `onAuthed({isNew})`. `App` then `navigate(isNew ? "onboard" :
"app")`. Fresh signups → onboarding wizard; returning logins → dashboard.
*(Gap: a returning user who never finished onboarding — has an account but no
project — currently lands on the dashboard, not onboarding. Minor; see changes.)*

## 9. After logout
`Settings → Sign out` → `api.logout()` (clears token) → `setAuthed(false)` →
`navigate("login")`. The app shows the Login screen. *(It does not return to the
public landing `/` — see changes: add a "back to site" affordance.)*

## 10. Unauthenticated user opens `/app`
Renders the Login screen (default tab: login). Correct.

## 11. Authenticated user opens the landing page
The landing is static HTML with no auth awareness — it shows marketing content
and the same CTAs. Not broken, but it doesn't offer a "Dashboard"/"Logout"
shortcut for a logged-in visitor. *(Minor polish opportunity; the app itself
stays under `/app`.)*

## 12. Will Vercel preserve routing? — THE KEY FINDING
**Not as-is.** The landing and dashboard are two separate artifacts, and the
landing CTAs use the absolute path `/app/...`. If they are deployed as two
separate Vercel projects (two `*.vercel.app` domains), then `/app/#/signup` on
the landing domain is a **dead link (404)** — exactly the "disconnected" problem
this task targets.

**Fix (single coherent deployment):** one Vercel project that serves
- `/` → landing (`index.html`, `landing.css`)
- `/docs/` → docs (static)
- `/app/` → the Vite dashboard **built with base `/app/`**
- a rewrite so `/app` and `/app/...` resolve to the dashboard `index.html`
  (SPA). Hash routing means `#/...` never reaches the server, so only the
  `/app/` base needs to resolve.

This is implemented via a small combined build script + `vercel.json` (see
changes / `PHASE4_PUBLIC_UX_COMPLETE.md`). No routing rewrite of the app itself
is needed — the hash router already does the right thing once `/app/` serves the
SPA shell.

## What already works (do NOT rebuild)
- Signup/login/auth/token, protected gate, logout, onboarding wizard
  (project→model→key-once→integrate→dashboard, all real backend calls),
  dashboard (Overview/Threats/Monitoring/Analytics/Feedback/Projects/Models/API
  Keys/Settings), honest empty states, error handling (`setErr`, `unauthorized`
  → re-login), API-key one-time reveal + copy.
- 18 frontend tests + Phase 3 live real-ML E2E already cover this.

## Minimal changes this pass (connect + polish only)
1. **Combined single-origin build for Vercel** (`vercel.json` + build script) so
   landing `/` and dashboard `/app/` ship as one deployment — makes every
   landing CTA a live link. *(the core fix)*
2. **Login → onboarding when the account has no project** (returning user who
   never finished setup), else dashboard. Small, backend-supported.
3. **"← Back to site" link** on the auth screen and a **home link** in the app
   so users can move between the marketing site and the app.
4. Frontend tests for the public-journey wiring.

No engine changes, no new features, no auth/onboarding rebuild.
