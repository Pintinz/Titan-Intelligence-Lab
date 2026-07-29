# TitanIQ — Authentication

Status: Live as of Milestone 6. Covers the dual-path authentication model, RBAC ladder,
Personal Access Tokens, Session Intelligence, and Security Intelligence. See
[rls.md](rls.md) for how role/ownership checks are mirrored at the database layer, and
[deployment.md](deployment.md) for the manual OAuth provider dashboard steps.

## 1. Two authentication paths, one `get_current_user` dependency

**Production path** — Supabase Auth (GoTrue) owns password verification, email verification,
magic links, and OAuth. FastAPI never sees or stores a real user's password. The flow:

1. Client authenticates directly against Supabase Auth (email/password, Google, or GitHub) and
   receives a Supabase-issued JWT.
2. Client calls the TitanIQ API with `Authorization: Bearer <supabase-jwt>`.
3. `apps.api.auth_deps.get_current_user` validates the JWT via `SupabaseJWKSValidator`
   (asymmetric, rotating JWKS keys fetched from `{project_url}/auth/v1/.well-known/jwks.json`).
4. `IdentityService.ensure_provisioned` get-or-creates the local `identity.users` shadow row,
   keyed by the JWT's `sub` claim — so `identity.users.id` always equals Supabase's
   `auth.users.id`, which is what lets `auth.uid()` line up directly with it in RLS policies.
5. If the JWT's `app_metadata.provider` indicates an OAuth provider (not `email`),
   `ensure_federated_identity_linked` idempotently records a `identity.federated_identities`
   row — safe to call on every login, never creates a duplicate.

**Offline/mock path** — `IdentityService.register`/`authenticate` (bcrypt-hashed passwords,
fully local). This exists specifically for the fast SQLite test suite and local dev without a
live Supabase project — same mock-first rationale as `fakeredis`/`FakeSportsProvider`
elsewhere (docs/decisions.md ADR-008, ADR-025). `POST /api/v1/auth/login` on this path returns
an `access_token` that is a short-lived **Personal Access Token**, not a Supabase JWT — it lets
a client authenticate subsequent requests through the same `Authorization: Bearer` header
without needing live Supabase credentials, reusing the PAT mechanism rather than inventing a
second bearer-token concept.

`get_current_user` tries JWT validation first (the common case), falling back to PAT lookup on
failure — the caller never needs to signal which kind of token it's sending.

## 2. RBAC ladder

Eight platform-wide roles, `modules.identity.domain.value_objects.Role`: Guest, Free, Rewarded,
Premium, Moderator, Analyst, Administrator, Super Administrator. Compared by ordinal (`level`),
never by enum identity, so a new role can be inserted without every call site needing a branch.
`apps.api.auth_deps.require_role(minimum)` gates a route to that ladder position or above.

Free/Rewarded/Premium are billing/entitlement tiers (`modules.billing`), not different platform
permissions — see [rls.md](rls.md) §1.

## 3. Personal Access Tokens

`identity.personal_access_tokens` — a raw token is shown to the user exactly once at creation
(`POST /api/v1/users/me/tokens`) and stored only as a SHA-256 hash (`Sha256TokenHasher`) —
fast, non-reversible, appropriate for a high-entropy generated secret (unlike a low-entropy
user password, which needs bcrypt's work-factor stretching). Tokens carry a `scopes` list, an
optional expiry, and can be revoked (`DELETE /api/v1/users/me/tokens/{id}`).

## 4. Session Intelligence

`identity.sessions` — one row per active login, materialized rather than derived from an event
log (same rationale as `ProviderHealthState` in `modules.admin`): device label, browser, IP,
user agent, a heuristic risk level (new IP relative to a user's other active sessions =
`MEDIUM`), created/last-seen/expiry timestamps. `GET /api/v1/users/me/sessions` lists a user's
own active sessions; `DELETE /api/v1/users/me/sessions/{id}` revokes one. Enabled for Realtime
(migration 0014) so a "log out everywhere" UX can update live across open tabs/devices.

## 5. Security Intelligence

`identity.security_events` (append-only) + `identity.account_lock_states` (materialized,
one row per user):

- Every login attempt (success or failure) is recorded, including failures against an email
  with no matching account.
- 5 consecutive failures locks the account for 15 minutes (`IdentityService.authenticate`
  checks the lock state before comparing passwords, so a locked account never even reaches
  password verification on subsequent attempts).
- Brute-force detection fires at 3 consecutive failures — deliberately **below** the lockout
  threshold, so it's an earlier, distinct signal rather than dead code (a threshold at or above
  the lockout point would never fire, since lockout blocks further failure recording once
  triggered — see docs/decisions.md for the bug this would otherwise be).
- A successful login clears the failure counter.

Both event types are Realtime-enabled and RLS-restricted to Moderator+ (never self-readable) —
see [rls.md](rls.md) §2.

## 6. OAuth providers

| Provider | Status |
|---|---|
| Email/Password, Magic Links, Email OTP | Enabled by default on every hosted Supabase project — no action taken or needed |
| Email verification required | On by default for hosted projects |
| Google | Code-side complete (`IdentityProvider.GOOGLE`, JWT `app_metadata.provider` mapping, auto-linking). Dashboard configuration (OAuth client id/secret) is a manual step — see [deployment.md](deployment.md) |
| GitHub | Same as Google |
| Apple, Microsoft | Code-side interfaces present (`IdentityProvider.APPLE`/`MICROSOFT`, `_SUPABASE_PROVIDER_MAP` in `apps.api.auth_deps` already maps Supabase's `azure` provider id to Microsoft) — no dashboard configuration done; flipping them on later is a config-only change once credentials exist |

No MCP tool available to this assistant can configure Supabase Auth provider settings — that
requires the Supabase Dashboard or the separate Management API. See
[deployment.md](deployment.md) for the exact manual steps.
