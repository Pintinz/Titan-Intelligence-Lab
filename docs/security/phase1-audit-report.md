# TitanIQ — Phase 1 Security Architecture Audit

**Date:** 2026-08-09
**Scope:** Enterprise Security & Compliance milestone, Phase 1 (audit only — no remediation applied yet).
**Method:** Direct code inspection (five parallel research passes across auth/tokens, RBAC/authorization,
database/RLS architecture, secrets/rate-limiting/headers/webhooks/billing, and audit-log coverage), cross-checked
against the existing [`docs/security.md`](../security.md) design doc. Every finding below is grounded in a
specific file:line citation found during this audit — nothing here is inferred or assumed.

This report supersedes nothing in `docs/security.md`; it documents where the **actual, current implementation**
diverges from that doc's stated intent, plus vulnerabilities that doc doesn't mention at all.

---

## 0. Architecture ground truth (read this before triaging anything below)

Two facts materially change how every finding below should be remediated:

1. **Supabase Postgres is the real production database, and RLS is real and extensively deployed
   (~96 tables) — but it is structurally inert for the FastAPI application.** The backend connects with a
   Postgres **superuser/service-role** connection string (`postgresql+asyncpg://postgres:<password>@...supabase.co`),
   which bypasses RLS unconditionally by Postgres design, for every request. The migration authors say this
   explicitly in their own comments (`backend/alembic/versions/0010_row_level_security.py:4-7`): RLS is
   defense-in-depth against a hypothetical direct-Postgres/PostgREST/Realtime access path, **not** the
   authorization boundary for the API. All real authorization for the FastAPI app lives in
   `apps.api.auth_deps.require_role`/`get_current_user` and per-service ownership checks.
   **Implication: "harden RLS" is not the correct remediation for any finding below unless explicitly noted —
   the fix belongs in application code.**
2. **Two authentication systems are simultaneously live in every deployment**, not one. Supabase Auth (JWT,
   production path, email-verification-enforced) and TitanIQ's own bcrypt-based `/api/v1/auth/register` +
   `/api/v1/auth/login` (originally intended "purely for the fast offline test suite," per
   `docs/security.md:12-14`) are both reachable with no environment gate
   (`backend/apps/api/main.py:137` mounts `identity_router` unconditionally). The bcrypt path has no email
   verification enforcement at all. This is the single highest-leverage architectural gap in the whole audit —
   several findings below (email verification bypass, enumeration, no password reset) only exist because of it.

---

## 1. Findings — CRITICAL

### C-1. Broken access control on subscription creation — free premium upgrade
- **Location:** `backend/apps/api/routers/billing_router.py:121-130` (`POST /api/v1/billing/subscriptions`), `backend/modules/billing/application/billing_service.py:80-110` (`BillingService.subscribe`)
- **Vulnerability:** The endpoint is guarded only by `Depends(get_current_user)` — any authenticated user of any role, including the default `FREE` tier. The request body (`SubscribeRequest`) lets the caller freely choose `subject_type`, `subject_id` (no check it equals the caller's own ID or an org they belong to), and `plan_key` (any plan, including paid tiers). `BillingService.subscribe()` performs no payment verification of any kind — there is no payment provider integrated at all (self-documented: `billing_service.py:1-6`, "charging a card is out of scope").
- **Attack scenario:** A signed-up free user sends `POST /api/v1/billing/subscriptions {"subject_type": "user", "subject_id": "<own-id>", "plan_key": "enterprise"}` and immediately receives an `ACTIVE` enterprise subscription, at zero cost, with no admin approval and no payment evidence. The same call with an arbitrary `subject_id` grants a subscription to any other user or organization.
- **Impact:** Total loss of billing integrity — revenue bypass, and (once entitlement checks are wired to real features, see C-2) unauthorized access to any subscription-gated capability.
- **Existing mitigation:** None at the endpoint. `create_plan`/`set_entitlement` on the same router are correctly `require_role(Role.ADMINISTRATOR)`-gated — the `subscribe` endpoint is the outlier.
- **Required remediation:** Either (a) gate self-service subscription creation to `subject_id == caller.id` (or a org the caller administers, via the same `TenancyService._require_role` pattern already used elsewhere) **and** require a verified payment-provider webhook/callback before setting status `ACTIVE`, or (b) restrict `POST /api/v1/billing/subscriptions` to `require_role(Role.ADMINISTRATOR)` until a real payment integration exists, with a separate, unprivileged "start checkout" endpoint that itself grants nothing.
- **Verification:** Automated test: unauthenticated → 401; `FREE`-tier user subscribing themselves to a paid plan with no payment token → 403/422; `FREE`-tier user subscribing a different `subject_id` → 403.

### C-2. Privilege escalation via unbounded role assignment
- **Location:** `backend/apps/api/routers/identity_router.py:116-128` (`POST /api/v1/users/{user_id}/role`), `backend/modules/identity/application/identity_service.py:377-393` (`IdentityService.change_role`)
- **Vulnerability:** The endpoint requires `require_role(Role.ADMINISTRATOR)`, but `change_role` never checks that `new_role <= actor.role`, and never checks `user_id != actor.id`.
- **Attack scenario:** Any `ADMINISTRATOR` calls `POST /api/v1/users/{own_id}/role {"role": "super_administrator"}` and is immediately promoted to the platform's highest tier — one that, per the RBAC audit, is otherwise never granted by any code path. The same call with another user's ID silently grants them administrator or super-administrator regardless of the actor's own actual authority over that decision.
- **Impact:** Full platform compromise from any single compromised/malicious `ADMINISTRATOR` account — there is effectively no ceiling below "grant yourself god mode."
- **Existing mitigation:** The action is audited (`AuditAction.ROLE_CHANGED`, with old/new role in metadata) — the event is logged, but not prevented. The frontend UI string claims role assignment is capped "up to your own privilege level" (`frontend/src/pages/ops/users-roles-page.tsx:48`) but this is enforced nowhere, frontend or backend.
- **Required remediation:** In `change_role`, reject if `new_role.level > actor.role.level`, and reject self-role-change entirely (or require a distinct, stricter check — e.g. `SUPER_ADMINISTRATOR`-only — for any change that reaches `ADMINISTRATOR`/`SUPER_ADMINISTRATOR`). This is also the natural place to finally give `SUPER_ADMINISTRATOR` a real, enforced meaning in application code (currently aspirational — defined in the `Role` enum and RLS SQL, required by zero FastAPI endpoints).
- **Verification:** Test: `ADMINISTRATOR` attempting to set their own role to `SUPER_ADMINISTRATOR` → 403; `ADMINISTRATOR` attempting to grant another user a role above their own → 403; `ADMINISTRATOR` granting a role at or below their own level → 200.

### C-3. Admin-only actions enforced only by frontend UI, not the API
- **Location:** `backend/apps/api/routers/market_router.py:137,202,217,232,244,256,268,280,310` (register/submit/approve/reject/promote/deprecate/archive/remove a market, map feature-to-market — `Depends(get_current_user)` only, `require_role` not even imported); `backend/apps/api/routers/prediction_router.py:177,195` (`approve_prediction`/`reject_prediction` — `Depends(get_current_user)` only, despite the file's own docstring calling these "Admin Actions"); confirmed reachable from the "admin-only" Prediction Laboratory UI (`frontend/src/router.tsx:255-262`, `RoleRoute minRole="administrator"`) whose backing calls (`GET /api/v1/markets`, `GET /api/v1/sports/{sport}/fixtures`, `POST /api/v1/predictions/generate`) all only require authentication.
- **Vulnerability:** This is precisely the anti-pattern the milestone brief names explicitly: "frontend hides the button, backend still serves it." The Prediction Laboratory route guard is real and correctly implemented client-side — but it is the *only* thing standing between a `FREE`-tier user and the full admin market-lifecycle and prediction-approval surface.
- **Attack scenario:** A signed-up free user, without ever touching the Ops/Prediction-Lab UI, calls `POST /api/v1/markets/{market_key}/promote` (or `/archive`, `/remove`) directly and mutates the platform's live production market catalog; or calls `POST /api/v1/predictions/{id}/approve` to publish a prediction that should require human admin sign-off.
- **Impact:** Full functional parity with an administrator for market lifecycle and prediction approval, obtainable by any authenticated user via direct API calls — no UI access required.
- **Existing mitigation:** None server-side. ~100 other admin endpoints across the codebase (`ml_platform_router.py`, `prediction_admin_router.py`, `main.py`'s `/api/v1/admin/*` surface — all 70 checked) are correctly `require_role(Role.ADMINISTRATOR)`-gated; these two files are the confirmed exceptions.
- **Required remediation:** Add `Depends(require_role(Role.ADMINISTRATOR))` to every mutating endpoint in `market_router.py` and to `approve_prediction`/`reject_prediction` in `prediction_router.py`. (Read-only `GET /api/v1/markets` and fixture listing can likely stay `get_current_user`-only — only the mutating actions need the role bump; confirm against product intent before applying broadly.)
- **Verification:** Test: `FREE`-tier user calling each of the 9 market-mutation endpoints and both prediction approve/reject endpoints directly → all 403; `ADMINISTRATOR` calling the same → 200.

---

## 2. Findings — HIGH

### H-1. IDOR: any user can revoke any other user's Personal Access Token
- **Location:** `backend/modules/identity/application/identity_service.py:352-358` (`revoke_personal_access_token`), called from `DELETE /api/v1/users/me/tokens/{token_id}` (`identity_router.py:194-200`)
- **Vulnerability:** The method fetches the token by ID and revokes it without ever comparing `token.user_id` to the calling `actor`. The `actor` parameter is used only for the audit-log entry, never for authorization.
- **Attack scenario:** An attacker who can enumerate or guess a token UUID (e.g., leaked in a bug report, log, or via timing) revokes another user's PAT, silently breaking their integrations.
- **Impact:** Availability/integrity — denial of service against another user's programmatic access, attributable in the audit log to the wrong actor's intent being hidden (the log records who did it, but nothing stopped it).
- **Existing mitigation:** None. The exact-same ownership-check pattern is correctly implemented elsewhere in this codebase (watchlist `unfollow`, alerts `mark_read`) — this is an inconsistency, not a missing capability.
- **Required remediation:** `if token.user_id != actor: raise NotTokenOwnerError` before revocation, mapped to 404 (not 403, to avoid confirming the token's existence) at the router layer — mirroring the watchlist/alerts pattern exactly.
- **Verification:** Test: User A creates a token; User B calls `DELETE /users/me/tokens/{A's token id}` → 404; token remains active; User A can still revoke their own token → 200.

### H-2. IDOR: any user can revoke any other user's session
- **Location:** `backend/modules/identity/application/identity_service.py:320-328` (`revoke_session`), called from `DELETE /api/v1/users/me/sessions/{session_id}` (`identity_router.py:150-156`)
- **Vulnerability/attack/impact:** Identical pattern and identical fix to H-1, applied to `Session` rows instead of PATs.
- **Required remediation:** `if session.user_id != actor: raise NotSessionOwnerError` before revocation, 404 on mismatch.
- **Verification:** Same shape as H-1's test, against the sessions endpoint.

### H-3. No rate limiting anywhere in the API
- **Location:** Confirmed absent repo-wide (no `slowapi`/`fastapi-limiter`/custom limiter dependency in `backend/pyproject.toml` or middleware stack); self-documented gap in `backend/apps/api/routers/public_router.py:16-21`.
- **Vulnerability:** `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, and the expensive `POST /api/v1/predictions/generate` (triggers ML inference and, per market, downstream Gemini calls) have no request-rate throttling. The only mitigation anywhere is the identity module's own per-account 5-attempt/15-minute lockout — which is per-account, not per-IP, so it does nothing against distributed credential stuffing or mass account creation.
- **Attack scenario:** Unlimited account creation for spam/abuse; distributed credential-stuffing across many accounts from one IP, or one account from many IPs; cost-exhaustion attack against `predictions/generate` by any authenticated user regardless of plan (compounds with C-1/H-9 — a free account can also hammer the most expensive endpoint in the system indefinitely).
- **Impact:** Availability and cost — no ceiling on compute/API spend an authenticated (or even anonymous, for registration) client can trigger.
- **Existing mitigation:** Per-account lockout on login only.
- **Required remediation:** Introduce a rate-limiting layer (e.g. `slowapi` or a small Redis-backed token-bucket, since Redis is already a dependency via the feature store) with tiers: strict IP-based limits on `/auth/register` and `/auth/login` (unauthenticated, cheap to abuse), and authenticated-user-based limits on `/predictions/generate` and other AI-adjacent endpoints, scaled by role/plan once entitlements are real. Internal ingestion workers should authenticate via a trusted service credential exempted from these limits (per the brief's Phase 11 instruction) rather than being rate-limited like public traffic.
- **Verification:** Test: N+1 rapid login attempts from a single simulated client → 429 before the account-lock threshold; registration burst → 429.

### H-4. Dual live authentication systems with no production gate; email verification is bypassable
- **Location:** `backend/apps/api/main.py:137` (unconditional mount), `backend/modules/identity/domain/entities.py:42-43` (`User.can_authenticate` allows `PENDING_VERIFICATION`), `identity_router.py:71-108`
- **Vulnerability:** The bcrypt auth path — described in `docs/security.md:12-14` as existing "purely for the fast offline test suite and non-Supabase dev" — is reachable on every deployment with no code path disabling it when Supabase is the intended production auth provider. It has no email-verification enforcement at all, so `POST /auth/register` → `POST /auth/login` yields a fully-functional bearer token (full-scope PAT, see H-6) with zero email ownership proof, on any live deployment.
- **Attack scenario:** Mass creation of unverified, fully-functional accounts against a production deployment, entirely bypassing whatever anti-abuse/verification guarantees the product depends on Supabase for.
- **Impact:** Undermines the stated security model in `docs/security.md` itself, not just a missing control.
- **Existing mitigation:** None currently gates this path off in non-dev environments.
- **Required remediation:** Either gate `identity_router` behind an explicit `TITANIQ_ENABLE_OFFLINE_AUTH` flag (default off, on only for tests/local dev — matching the doc's stated intent), or, if this path must stay reachable in production for some reason, build a real email-verification flow for it (token issuance + `/verify-email` endpoint + enforcement in `can_authenticate`) so it stops being a strictly weaker parallel system.
- **Verification:** With the flag unset (prod-like config), `POST /auth/register`/`/auth/login` → 404/disabled; with it set (test config), existing behavior unchanged (verify existing test suite still passes).

### H-5. Entitlement checks exist but gate nothing
- **Location:** `backend/modules/billing/application/billing_service.py:128-146` (`has_feature`/`check_within_limit`/`record_usage`) — grepped against every router; the only call sites are inside `billing_router.py` itself (an informational read endpoint). `prediction_router.py`'s `generate` endpoint and every other feature/AI-adjacent router call none of these.
- **Vulnerability:** Even setting aside C-1 (anyone can grant themselves a subscription for free), the subscription state that *is* correctly computed server-side in `BillingService` is never actually consulted anywhere a real resource is served.
- **Impact:** Paid-tier gating is currently decorative — every authenticated user, on any plan or none, has identical access to every feature this data model was built to differentiate.
- **Required remediation:** Wire `has_feature`/`check_within_limit` (and `record_usage`) into the actual protected endpoints (starting with `predictions/generate`) once C-1 is fixed and the entitlement model is trustworthy.
- **Verification:** Test: user with no subscription hitting a plan-gated endpoint → 402/403; user with the required plan → 200.

### H-6. PAT scopes are declared but never enforced
- **Location:** `backend/modules/identity/domain/entities.py:74-98` (`has_scope`, zero call sites outside its own definition, confirmed by repo-wide grep)
- **Vulnerability:** Any valid, non-expired, non-revoked PAT authenticates as the full user regardless of its declared `scopes` — including the offline-login-flow token, which is created with wildcard scope `["*"]` (`identity_router.py:99`).
- **Impact:** A token a user or integration believes is narrowly scoped is, in practice, equivalent to a full-access credential — misleading and a real blast-radius amplifier if any single narrowly-intended token leaks.
- **Required remediation:** Enforce `token.has_scope(required_scope)` in `get_current_user`/`require_role` (or at minimum in a scoped-dependency variant used by sensitive routes) before this feature is presented to users as meaningful.
- **Verification:** Test: a token created with `scopes=["read:predictions"]` used against a mutating endpoint → 403.

### H-7. IDOR-shaped gap: no organization-membership check on webhook management
- **Location:** `backend/apps/api/routers/webhooks_router.py:66-113`
- **Vulnerability:** Every endpoint (register, list, rotate-secret, deactivate) is guarded only by `Depends(get_current_user)`, with **no check that the caller belongs to the `organization_id` in question** — unlike `tenancy_router.py`, which correctly enforces org-role checks via `TenancyService._require_role` for equivalent operations.
- **Attack scenario:** Any authenticated user registers a webhook endpoint against an arbitrary organization's ID, or rotates/deactivates another org's existing webhook endpoint by guessing its ID.
- **Impact:** Cross-tenant tampering with webhook delivery configuration.
- **Required remediation:** Apply the same `TenancyService._require_role`-style membership check used elsewhere in the codebase to every `webhooks_router.py` endpoint.
- **Verification:** Test: user not a member of Org B attempting to register/rotate/deactivate a webhook for Org B → 403.

### H-8. User-created Personal Access Tokens never expire
- **Location:** `backend/apps/api/routers/identity_router.py:159-172` (`CreateTokenRequest` has no `expires_at` field at all; `create_personal_access_token` defaults it to `None`)
- **Vulnerability:** Only the internal offline-login PAT gets an expiry (12 hours); every user-created token via the API/UI is a permanent credential by default, with no way to set an expiry even if the user wanted to.
- **Impact:** Indefinite-lifetime bearer credentials compound the blast radius of any leak.
- **Required remediation:** Add an optional (or, for new tokens, mandatory with a sane default like 90 days) `expires_at` to the creation request/UI; consider a maximum enforced ceiling.
- **Verification:** Test: token creation without an explicit expiry gets a default expiry, not `None`.

---

## 3. Findings — MEDIUM

| ID | Location | Summary | Remediation direction |
|---|---|---|---|
| M-1 | `backend/apps/api/main.py` (no security-headers middleware exists) | No CSP, HSTS, X-Content-Type-Options, Referrer-Policy, or X-Frame-Options set anywhere; only `CORSMiddleware` is registered. | Add a small custom Starlette middleware (or configure at the reverse-proxy/CDN layer) setting these headers on every response. |
| M-2 | `apps/api/auth_deps.py:90-100` (`require_role`'s 403 path) | No audit/security event is ever recorded when a 403 fires — privilege-escalation probing against admin endpoints is invisible in the audit trail. | Emit a `PERMISSION_DENIED`-class event (new `AuditAction`/`SecurityEventType` member) from the 403 path, including actor, attempted resource, and required vs. actual role. |
| M-3 | `identity_service.py:320-328` / Settings → Security UI | Session revocation only flips a DB flag — it doesn't invalidate any actual token, and the Supabase JWT auth path never creates a `Session` row at all, so the "Active sessions" panel is non-functional for real production users. | Either link `Session` rows to the credential they represent so revocation is meaningful, or (simpler) remove/relabel the panel until Supabase-path session tracking is real, to avoid a false sense of control. |
| M-4 | `identity_router.py:76-77` (`POST /auth/register` 409 body) | "Account already exists for {email}" enables email enumeration via the registration endpoint (login already avoids this correctly). | Return a generic success/ambiguous response, or a uniform error, regardless of whether the email is already registered. |
| M-5 | Audit logging, 4 fragmented tables (`identity.audit_log_entries`, `identity.security_events`, `predictions.prediction_audits`, `ingestion.timeline_events`) | No unified audit concept; large swaths of the app (feature flags, data export, model rollback, 403s, ops/admin dashboard *access* itself) are never audited despite several having dead `AuditAction` enum values implying they should be. No API endpoint exposes the raw audit trail to anyone — only an aggregate, ungated action-count summary exists. | Not a quick fix — needs a scoped follow-up: (a) emit audit events from the currently-silent admin mutation paths (feature flags, export, rollback) using the existing shared `AuditLogEntry` pattern; (b) add an `require_role(Role.ADMINISTRATOR)`-gated read endpoint for the audit trail itself. |
| M-6 | `backend/alembic/versions/0027_watchlist.py`, `0028_alerts.py` | These two schemas were added after the RLS migration series and never got RLS enabled, unlike every other schema. Zero practical impact today (RLS is bypassed by the backend anyway, §0), but breaks the "every table has RLS" invariant the rest of the codebase maintains. | Backfill a migration enabling RLS + ownership policies on `watchlist.watchlist_entries` and `alerts.alert_events`, mirroring the pattern in `0010_row_level_security.py`. |
| M-7 | `identity_router.py:81-108` (`/auth/login` doesn't inject `Request`) | Login `SecurityEvent`s never capture IP/user-agent — the login endpoint doesn't pass a `Request` object through to `IdentityService.authenticate`, so brute-force/suspicious-login telemetry is blind to source IP entirely. | Thread `Request` (or extracted `ip_address`/`user_agent`) from the router into `authenticate()`. |
| M-8 | `tenancy_router.py:121-127` (`list_members`) | Any authenticated user can list any organization's members by ID — no membership check, unlike every other tenancy endpoint. | Apply the same `_require_role`-or-equivalent membership check used elsewhere in `TenancyService`. |

## 4. Findings — LOW

| ID | Location | Summary | Remediation direction |
|---|---|---|---|
| L-1 | `backend/.env.example` | Does not exist (only `frontend/.env.example` is tracked). New backend deployers have no git-tracked reference for required `TITANIQ_*` vars. | Add `backend/.env.example` with variable names only, no real values (Phase 8 deliverable). |
| L-2 | `backend/apps/api/main.py:122-134` (`allow_credentials=True`) | Pre-provisioned for a future cookie-based flow that doesn't exist yet; widens blast radius if `TITANIQ_CORS_ORIGINS` is ever misconfigured in production. | Set `allow_credentials=False` until a cookie-based flow is actually built, or tightly audit the production value of `TITANIQ_CORS_ORIGINS` at deploy time. |
| L-3 | Offline/bcrypt auth path | No password-reset mechanism exists for accounts on this path — no way to recover a forgotten password. | Low priority given H-4's broader recommendation (gate this path off production entirely) makes this moot if adopted. |
| L-4 | `PredictionAudit.actor` (`predictions/domain/entities.py:268`) | Free-text `str` rather than a `UserId` reference, inconsistent with the identity module's audit shape. | Cosmetic/consistency issue, not a security hole — low priority. |

## 5. Findings — INFORMATIONAL

| ID | Location | Summary |
|---|---|---|
| I-1 | `frontend/.env.example:1-8` | Contains a real (but intentionally browser-safe, `sb_publishable_`-prefixed) Supabase project URL and key rather than placeholder values. Not a credential-compromise risk (RLS is the actual boundary for that key), but unusual practice and discloses the specific Supabase project ID to anyone reading the public repo. |
| I-2 | `backend/apps/api/routers/webhooks_router.py` | No inbound webhook receivers exist yet in the product (only outbound dispatch to partner endpoints, correctly HMAC-SHA256-signed with constant-time comparison). The signature-verification code is sound but has no real attack surface to defend today — revisit when an inbound payment/provider webhook is added. |
| I-3 | Secrets handling generally | No hardcoded secrets found anywhere in source; nothing leaked into the frontend bundle (verified against shipped `dist/assets/*.js`, not just source); nothing found in git history; provider credentials are correctly vault-encrypted and never logged, including a deliberate anti-leak precaution in the Gemini adapter's error handling. This area is in good shape — called out here so it isn't lost among the negative findings above. |

---

## 6. What's already handled well (do not weaken these while fixing the above)

- Bcrypt (cost 12) for password hashing; SHA-256 for high-entropy PATs — both correct choices for their respective threat models.
- Supabase JWT validation uses asymmetric JWKS (ES256/RS256) with issuer/audience checks — never a static shared secret.
- Account lockout checks lock state *before* password comparison (avoids timing oracle + wasted bcrypt work).
- Login (not registration) error messages already avoid user enumeration.
- CORS is a real, environment-driven origin allowlist — not a wildcard misconfiguration.
- Watchlist and Alerts correctly implement the ownership-check pattern that PATs/Sessions are missing (H-1/H-2) — use them as the reference implementation for the fix.
- Provider credentials: vault-encrypted at rest, masked in every API response, never logged — confirmed end-to-end from storage through to the Gemini adapter's error-handling.
- ~100 of the ~105 admin-tier endpoints checked across the codebase are correctly `require_role`-gated; the RBAC gaps found (C-3, H-3-adjacent) are real but narrow, not systemic.
- Audit entries never leak secrets into their metadata (checked every call site).

---

## 7. Recommended sequencing (not yet actioned — pending scope confirmation)

Given the size of the full 26-phase brief, remediation should land in scoped batches rather than one pass:

1. **Batch 1 (small, high-confidence, mirrors existing patterns in the same codebase):** H-1, H-2 (PAT/session IDOR — one-line owner checks), C-2 (role-escalation ceiling check), C-3 (add missing `require_role` to `market_router.py` + `prediction_router.py` approve/reject), M-4 (registration enumeration). These are narrow, low-risk, test-covered fixes.
2. **Batch 2 (C-1/H-5 billing):** requires a product decision (block self-service subscribe entirely vs. build minimal payment-verification gate) before implementation — flagged for your input below.
3. **Batch 3 (infrastructure):** H-3 rate limiting, M-1 security headers — new but self-contained infrastructure, no product decisions needed.
4. **Batch 4 (larger, needs scoping):** H-4 (dual-auth production gate), audit-log unification/coverage (M-2, M-5), H-6/H-8 (PAT scope enforcement + expiry), H-7 (webhook org-membership), remaining MEDIUM/LOW items, plus the doc/test-suite/dependency-scan deliverables from Phases 18-22.
