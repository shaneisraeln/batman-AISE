# BATMAN — Phase 2 Security Audit

Scope: the hosted multi-tenant product (control plane + data plane), the SDK,
persistence, and deployment. This documents the security controls actually
implemented, where they live, and the tests that exercise them.

**Test coverage referenced below:** 103 automated tests pass
(84 server/main + 13 SDK + 6 ML-service), including the security-focused cases
called out per control.

---

## 1. Authentication

### User authentication
- Passwords hashed with **PBKDF2-HMAC-SHA256**, per-password random salt,
  240,000 iterations — `batman/cloud/crypto.py::hash_password`. Verification is
  constant-time (`hmac.compare_digest`).
- Session tokens are **stateless, HMAC-SHA256 signed** with an expiry, signed by
  `BATMAN_SECRET_KEY` — `issue_token` / `verify_token`. Tampered or expired
  tokens are rejected.
- Login is written to reduce user enumeration (always runs a verify).
- Tests: `test_cloud_service.py::test_password_hash_roundtrip`,
  `test_short_password_rejected`, `test_token_roundtrip_and_tamper`,
  `test_login_wrong_password`.

### API-key authentication (data plane)
- Keys are cryptographically random, prefixed `bm_live_`
  (`batman/gateway/auth.py::generate_api_key`).
- Only a **SHA-256 hash** is stored; the raw key is returned **once** at
  creation and is never persisted or logged.
- Verification is **constant-time** (`hmac.compare_digest` in `verify_key_hash`).
- Keys are **revocable**; revoked/expired keys are rejected at the data plane.
- Tests: `test_auth.py` (hash/verify/lifecycle), `test_cloud_api.py::test_data_plane_rejects_bad_key`, `test_revoked_key_denied`.

---

## 2. Tenant isolation

- Every control-plane resource read/write is scoped to the authenticated user:
  repositories expose `get_owned(id, user_id)` and `list_for_user` /
  `list_for_project` filtered by `user_id`
  (`batman/db/repositories.py`).
- The service layer verifies project/model ownership before creating models or
  keys and before configuring upstreams (`batman/cloud/service.py`).
- Telemetry reads are filtered to the caller's `project_ids`
  (`TelemetryRepository.get_threats/metrics_summary(project_ids=)`); the
  per-incident detail endpoint checks project ownership before returning a row.
- Tests: `test_db.py::test_tenant_isolation_projects/_models`,
  `test_cloud_service.py::test_cannot_use_another_users_project`,
  `test_key_revocation_is_tenant_scoped`,
  `test_cloud_api.py::test_tenant_cannot_see_others_projects`,
  `test_cloud_e2e.py::test_e2e_tenant_isolation_of_telemetry`.

---

## 3. Secret handling & logging

- **API keys** travel only in the `x-api-key` header. The SDK never logs the
  key and redacts it in `repr()` and errors (`batman_ml/client.py::_redact`).
- Structured logging redacts sensitive keys (`api_key`, `token`, `secret`,
  `password`, …) — `batman/telemetry/logger.py`.
- **Key listing** never returns the hash or the raw secret
  (`ApiKeyRepository.list_for_user`). Test:
  `test_db.py::test_api_key_repo_never_returns_hash_in_listing`,
  `test_cloud_api.py::test_full_control_plane_flow` (asserts no `key_hash`).
- No secrets are committed: `.env`, `.env.cloud` and `*.db` are gitignored;
  `.env.cloud.example` carries only placeholders.

---

## 4. Upstream credential protection

- Credentials for a customer's existing ML API are **encrypted at rest** with
  **Fernet** (`batman/cloud/crypto.py::encrypt_secret`), keyed by
  `BATMAN_ENCRYPTION_KEY`.
- The system **fails closed**: if `cryptography` is missing or the key is unset,
  storing an upstream secret raises rather than persisting plaintext.
- Secrets are decrypted **transiently in-memory** only to build the upstream
  request headers (`batman/cloud/upstream.py::_auth_headers`); they are never
  returned by any endpoint or logged.
- Tests: `test_cloud_service.py::test_upstream_secret_is_encrypted_at_rest`,
  `test_cloud_api.py::test_upstream_header_auth_encrypted_and_applied`.

---

## 5. Input validation

- All client input is treated as untrusted and validated: schema, numeric
  coercion, dimensionality, payload-size cap, NaN/Inf, and configurable bounds
  (`batman/gateway/validation.py::validate_request`). Failures become
  security events rather than opaque errors.
- Tests: `test_validation.py` (6 cases).

---

## 6. Rate limiting

- Sliding-window + burst limiter per API key / session
  (`batman/gateway/rate_limit.py`), enforced on the data plane.
- A separate limiter throttles control-plane auth endpoints (signup/login) to
  resist brute force (`batman/cloud/app.py` `control_limiter`).
- Tests: `test_rate_limit.py` (burst, sustained, per-key independence).

---

## 7. Enforcement integrity (LLM boundary)

- The **policy engine is authoritative**. The LLM investigation layer is
  advisory: it explains and recommends but cannot change the action
  (`batman/agents/response_agent.py`, `orchestrator.py`).
- Blocked requests never reach the protected model: the data plane runs
  detection first and only invokes the upstream adapter when
  `decision.allowed()` — `batman/cloud/app.py::/v1/predict`.
- Test: `test_agents.py::test_orchestrator_llm_cannot_bypass_policy`,
  `test_cloud_e2e.py::test_e2e_security_extraction_enforced`.

---

## 8. Data handling & retention

- Telemetry stores behavioral **features and decisions**, not raw inference
  payloads by default (`batman/telemetry/schema.py`).
- Model **predictions are returned to the caller and not persisted**.
- Telemetry is immutable; analyst **feedback is stored separately** and is used
  only for future evaluation, never automatic retraining.
- Operators should configure retention per their policy; sensitive raw inputs
  should not be sent unless required.

---

## 9. Transport & deployment

- Production deployment terminates **HTTPS** at the Caddy reverse proxy
  (`deploy/Caddyfile`), which provisions/renews TLS automatically for a real
  domain. Basic security headers are set (nosniff, X-Frame-Options, referrer
  policy, server header suppressed).
- Secrets are supplied via environment / `.env` (gitignored), never baked into
  images.
- PostgreSQL is the production datastore; the stack was verified end-to-end on
  Postgres in containers (all 7 tenancy/telemetry tables created; full
  signup→key→predict→metrics flow succeeded).

---

## 10. Residual risks / recommendations

- **Secret key management**: `BATMAN_SECRET_KEY` and `BATMAN_ENCRYPTION_KEY`
  must be strong and stored in a real secret manager for production; rotating
  `BATMAN_ENCRYPTION_KEY` requires re-encrypting stored upstream secrets.
- **Session state / rate-limit state** is in-process; a multi-replica
  deployment should move it to a shared store (e.g. Redis) for consistent
  enforcement.
- **Token revocation**: tokens are stateless with expiry; add a denylist if
  immediate session revocation is required.
- **Threshold calibration**: detection thresholds must be tuned per protected
  model's traffic — run in `monitor` mode first.

---

## Verdict

The Phase-2 product implements authentication, tenant isolation, secret
protection, encrypted upstream credentials, input validation, rate limiting, and
an authoritative policy boundary, with automated tests covering each. The
detection engine from Phase 1 is unchanged and its 49 tests remain green.
