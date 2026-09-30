# BATMAN — Public User Journey

The end-to-end path a brand-new developer takes, with no internal knowledge and
no manual URLs. Everything below is one coherent product on a single origin
(`/` landing, `/app/` dashboard, `/docs/` docs).

```
Visitor
  │  opens https://<site>/           (landing page)
  ▼
Landing  ── "Get Started" → /app/#/signup   ·   "Log in" → /app/#/login
  │
  ▼
Signup   (POST /auth/signup)         → account created, token stored
  │
  ▼
(Login)  (POST /auth/login)          → returning users; token stored
  │        no project yet → Onboarding ; has project → Dashboard
  ▼
Onboarding wizard  (first run)
  │  Project   → POST /projects
  │  Model     → POST /models
  │  API Key   → POST /keys   (shown once, copy button)
  │  Integrate → real SDK + REST snippets using the new key
  ▼
Dashboard  (/app)                    → real tenant data, honest empty states
  │
  ▼
Integration → client sends inference (SDK / REST) with the API key
  │
  ▼
Inference  (POST /v1/predict)        → BATMAN detection + policy → real model
  │
  ▼
Telemetry  (GET /v1/metrics, /v1/threats)  → shown in Analytics / Threats
  │
  ▼
Threat     (suspicious traffic)      → detected, enforced (403/429), recorded
  │
  ▼
Feedback   (POST /v1/feedback)       → analyst labels the detection
```

## Stage notes

- **Landing** — static marketing page; honest positioning (what BATMAN is /
  does / does **not** claim). Nav: How it works · Detection · Integrate ·
  Limitations · Log in · **Get Started**. Every CTA is a live same-origin link
  into the app; no dead links, no manual routes.
- **Signup / Login** — the real auth screen (`/app/#/signup` or `#/login`).
  Bearer token stored in `localStorage`. A "← Back to site" link returns to `/`.
- **Routing after auth** — fresh signup → onboarding. Returning login → the
  dashboard, unless the account has **no project yet**, in which case it also
  goes to onboarding so nobody lands on an empty dashboard.
- **Onboarding** — 4 real steps (project → model → API key → integrate). The API
  key is shown exactly once with a copy action. Auto-skips ahead if the account
  already has data. "skip for now" and "Enter the Batcave" both reach the app.
- **Dashboard** — Overview / Threats / Monitoring / Analytics / Feedback /
  Projects / Models / API Keys / Settings. All data is fetched from the real
  backend; brand-new accounts see honest empty states, never fabricated numbers.
- **Integration** — snippets match the real `batman-ml` SDK (`protect`,
  `BatmanClient`) and the REST contract (`x-api-key`, `POST /v1/predict`).
- **Inference → Telemetry → Threat → Feedback** — real requests flow through the
  frozen Phase 1 detection engine to the protected model; suspicious traffic is
  detected and enforced; telemetry is tenant-scoped and request-traceable;
  analysts can label detections.
- **Revoke / Logout** — revoking a key makes reuse return 401; logout discards
  the token and protected routes require login again.

## Protected vs public routes

- Public: `/` (landing), `/docs/`.
- App shell: `/app/` (served to everyone), but every dashboard **view** is gated
  client-side on the token, and the backend independently rejects any
  unauthenticated or revoked-key request. A logged-out visitor at `/app/` sees
  only the login/signup screen.
