# BATMAN Phase 3 — Pre-Public-Launch Security Audit

**Scope:** the Phase 2 cloud layer (control plane + multi-tenant data plane), the
dashboard build/test toolchain, and deployment configuration. The Phase 1
detection engine is **frozen** and was not modified.

**Method:** code review + executable adversarial tests. Every claim below is
backed by a test in `tests/test_security_*.py` (run: `.venv\Scripts\python -m
pytest tests/test_security_phase3.py tests/test_security_isolation.py
tests/test_security_cors_upstream.py tests/test_security_ssrf.py -q`).

**Labels:** VERIFIED (proven by a passing test) · RESIDUAL (known, accepted,
documented) · MVP-LIMITATION (deliberate scope boundary).

**Security test count added this phase:** 56 (16 auth/key/rate/size + 13 tenant
isolation + 7 CORS/upstream + 20 SSRF). Full backend suite: **148 passed, 7
skipped**; Phase 1 engine (49 tests) unchanged and green.

---

## Material hardening changes made in Phase 3

Two real defects/gaps were fixed (both in the cloud layer, not the engine):

1. **Expired API keys were accepted on the data plane.** `authenticate_api_key`
   checked only `status == "active"` and ignored `expires_at`. Fixed to also
   reject via `is_expired(record)`. *(test_expired_api_key_denied)*
2. **SSRF: upstream URLs were unvalidated.** A tenant could point their model's
   upstream URL at loopback, private, or cloud-metadata addresses. Added
   `batman/cloud/ssrf.py` and enforced it in `set_upstream`. *(test_security_ssrf.py)*

Plus one defensive addition:

3. **Unbounded predict input.** `/v1/predict` now bounds rows/cols (413 on
   oversize). *(test_oversized_predict_*)*
4. **Key-farming.** `/keys` creation is now rate-limited per user.
   *(test_key_generation_is_rate_limited)*

---

## 1. Authentication — VERIFIED

| Control | Status | Evidence |
|---|---|---|
| Passwords hashed (PBKDF2-HMAC-SHA256, 240k rounds, per-pw salt, constant-time verify) | VERIFIED | `crypto.py`; `test_password_is_hashed_not_stored_plaintext` |
| Passwords never stored/returned in plaintext | VERIFIED | `UserRepository` stores `password_hash` only |
| Short passwords rejected (min 8) | VERIFIED | `test_short_password_rejected` (422) |
| Protected endpoints require Bearer token | VERIFIED | `test_protected_routes_require_bearer` |
| Tampered token rejected | VERIFIED | `test_tampered_token_rejected` (HMAC mismatch → 401) |
| Expired token rejected | VERIFIED | `test_expired_token_rejected` |
| User-enumeration resistance (login runs dummy verify for missing user; identical error) | VERIFIED | `test_invalid_credentials_do_not_reveal_user_existence` |
| Auth error bodies don't leak the valid token | VERIFIED | `test_auth_error_bodies_do_not_leak_secrets` |

**Token design (MVP-appropriate):** stateless HMAC-SHA256 tokens signed by
`BATMAN_SECRET_KEY`, 7-day expiry, verified on every request. Logout is a
client-side token discard (the API is stateless). This is deliberately simple
and adequate for the MVP.

- **RESIDUAL:** stateless tokens cannot be individually revoked before expiry
  (only global secret rotation invalidates all). Acceptable for MVP; a
  server-side session/denylist is future work if instant revocation is needed.
- **RESIDUAL:** if `BATMAN_SECRET_KEY` is unset, crypto falls back to a known
  dev secret. Production must set it — enforced/guided in Phase C.

## 2. API keys — VERIFIED

| Control | Status | Evidence |
|---|---|---|
| Only SHA-256 hash stored; raw key returned once | VERIFIED | `gateway/auth.py`; `test_api_key_full_lifecycle...` |
| Full lifecycle create→display→use→revoke→reuse-denied | VERIFIED | `test_api_key_full_lifecycle...` |
| Expired keys denied on data plane | VERIFIED (fixed) | `test_expired_api_key_denied` |
| Invalid / missing keys → 401 | VERIFIED | `test_invalid_and_missing_api_keys_denied` |
| Keys never in list response / telemetry / threat detail | VERIFIED | `test_api_key_never_appears_in_telemetry_or_threat_detail` |
| Keys cannot cross tenant boundaries | VERIFIED | tenant-isolation suite |

## 3. Tenant isolation — VERIFIED (adversarial)

Attacker B, using B's own valid bearer token and API key, is DENIED on every
one of A's resources (projects, models, keys create/revoke/list, upstream,
telemetry, metrics, threats list + detail, feedback Bearer + data-plane). 13
adversarial tests in `test_security_isolation.py`. A's key still works after B's
failed revoke attempt.

## 4. CORS — VERIFIED

- Never wildcard; `allow_origins` comes from `BATMAN_CORS_ORIGINS`.
- `allow_credentials=True` is safe because origins are always explicit (the
  dangerous `*` + credentials combination never occurs).
- Configured origin is echoed; an unconfigured origin is not.
- Evidence: `test_security_cors_upstream.py` (4 CORS tests) +
  `test_cors_origins_are_not_wildcard`.

## 5. Upstream credential security — VERIFIED

- Encrypted at rest with Fernet; plaintext never persisted.
- Never returned in the set response, models list, or telemetry.
- Decrypts only in memory at request time (`upstream.py::_auth_headers`).
- **Fails closed** (503) when `BATMAN_ENCRYPTION_KEY` is unavailable — never
  writes plaintext.
- Evidence: `test_upstream_secret_encrypted_and_never_returned`,
  `test_upstream_secret_not_in_telemetry`,
  `test_upstream_secret_fails_closed_without_encryption`.

## 6. SSRF — VERIFIED (mitigated this phase)

`batman/cloud/ssrf.py::validate_upstream_url` runs at `set_upstream`:

- Only `http`/`https` schemes (blocks `file://`, `ftp://`, `gopher://`,
  `redis://`, …).
- Blocks literal IPs that are loopback / private (RFC1918) / link-local
  (incl. cloud metadata `169.254.169.254`) / reserved / multicast / unspecified.
- Blocks `localhost` and `*.localhost`.
- Resolves DNS hostnames (`socket.getaddrinfo`) and blocks any that resolve to a
  blocked address (defeats config-time DNS pointing at private ranges).
- Fails closed on unresolvable hosts when the guard is active.
- Endpoint returns **400** on a rejected URL.

**Escape hatch:** `BATMAN_ALLOW_PRIVATE_UPSTREAM=1` disables the private-range
block for local dev / docker where the protected model is legitimately on a
private network (e.g. the bundled ml-service). **OFF by default**, so production
is protected unless an operator explicitly opts in. The production cloud compose
stack does not bundle ml-service, so the guard stays on in production.

- **RESIDUAL (documented, MVP-appropriate):** this is validation, not a full
  egress firewall. It does not defend against TOCTOU DNS-rebinding between
  validation and the actual request, or a public URL that 3xx-redirects to a
  private host. A hardened deployment should also restrict egress at the network
  layer (security group / NAT / egress proxy). 20 tests in `test_security_ssrf.py`.

## 7. Input / request security — VERIFIED

- `/v1/predict` bounds request size: > `BATMAN_MAX_PREDICT_ROWS` (default 1000)
  or > `BATMAN_MAX_PREDICT_COLS` (default 4096) → **413**.
- Malformed JSON / wrong types → FastAPI/pydantic 422 (framework-level).
- Upstream errors are surfaced as **502** (`upstream_error`) and are clearly
  distinct from BATMAN's own **403** BLOCK decision.
- Evidence: `test_oversized_predict_row_count_rejected`,
  `test_oversized_predict_col_count_rejected`.

## 8. Rate limiting — VERIFIED (strengthened)

| Endpoint | Protection |
|---|---|
| `/auth/signup` | control limiter (30 rpm / 8 burst) — VERIFIED 429 |
| `/auth/login` | control limiter, keyed per email — VERIFIED 429 |
| `/keys` (generation) | control limiter, keyed per user (added this phase) — VERIFIED 429 |
| `/v1/predict` | engine per-key sliding-window limiter (`BATMAN_RL_RPM`=60 / burst 10) |
| `/v1/feedback` | Bearer-gated (valid token required); not separately throttled |

- **MVP-LIMITATION:** the limiter is **in-memory per process** — it does not
  coordinate across multiple workers/replicas. A multi-instance production
  deployment needs a shared store (e.g. Redis) or an edge rate limiter (Caddy /
  API gateway). Documented; not a launch blocker for a single-instance MVP.

## 9. Logging — VERIFIED

- `telemetry/logger.py` emits structured JSON and **redacts**
  `api_key / raw_key / authorization / secret / password / token`.
- Telemetry persists only **engineered behavioral features** + scores /
  action / threat / latency — **never raw inference inputs** (explicit privacy
  principle in `telemetry/schema.py`).
- Engine errors log a code (`model_predict_failed`) with no payload.
- **RESIDUAL (documented):** the per-session behavioral state keeps a bounded
  in-memory window of recent input vectors (needed for similarity/diversity in
  extraction detection). This is transient RAM only — never written to the DB
  or logs.

## 10. Dependency audit (dashboard npm) — DOCUMENTED, NOT FORCE-UPGRADED

`npm audit` reports **5 vulnerabilities** in the dashboard:

| Package | Severity | Direct | Class | Fix | Breaking? |
|---|---|---|---|---|---|
| `vitest` | critical | dev | test runner: arbitrary file read via Vitest UI server / `@vitest/mocker` | vitest 5.x | **major (2→5)** |
| `vite` | high | dev | dev-server path traversal / `server.fs.deny` bypass / launch-editor NTLM | vite 8.x | **major (5→8)** |
| `@vitest/mocker` | moderate | transitive | via vitest | vitest 5.x | major |
| `esbuild` | moderate | transitive | dev-server request forgery | vite 8.x | major |
| `vite-node` | moderate | transitive | via vitest | vitest 5.x | major |

**Assessment:**
- `npm audit --omit=dev` → **0 vulnerabilities**. All five are in the
  **dev/test toolchain**.
- They affect a *running Vite dev server or Vitest UI on a developer machine* —
  **not** the shipped artifact. The production dashboard is a static
  `vite build` output served by nginx/`serve`; none of the vulnerable
  dev-server code runs in production.
- Production runtime deps (`react`, `react-dom`, `recharts`) have **0** known
  vulnerabilities.
- Every fix is `isSemVerMajor: true` (vite 5→8, vitest 2→5) and would likely
  break the test setup.

**Decision:** do **not** run `npm audit fix --force`. Forcing a breaking major
upgrade to zero the count would risk the (currently green) test suite for no
production risk reduction. Tracked as **accepted dev-only risk**; revisit when
migrating to vite 8 / vitest 3+ deliberately. Developers should not expose the
Vite dev server or Vitest UI on untrusted networks.

---

## Production blockers status

- **SSRF** — was the top blocker → **MITIGATED + tested.**
- **Expired-key enforcement** — was a gap → **FIXED + tested.**
- No remaining *critical* production-blocking security defect is known at the
  application layer.
- Operational must-dos before public launch (Phase C/D/E): set a strong
  `BATMAN_SECRET_KEY` + `BATMAN_ENCRYPTION_KEY`, keep `BATMAN_ALLOW_PRIVATE_UPSTREAM`
  OFF, set explicit `BATMAN_CORS_ORIGINS`, run behind HTTPS (Caddy), and add an
  edge/shared rate limiter if running multiple instances.
