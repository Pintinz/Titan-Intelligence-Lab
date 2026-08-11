# TitanIQ — Security

Status: Identity, RBAC, RLS, audit, session/security intelligence, and Personal Access Token
infrastructure live as of Milestone 6 (see [supabase.md](supabase.md), [rls.md](rls.md),
[authentication.md](authentication.md)). Full review gate remains before Milestone 20
(production launch). Security is designed into every layer, not appended before launch.

## 1. Authentication & Authorization

- **AuthN**: Supabase Auth (JWT-based, asymmetric JWKS validation — `SupabaseJWKSValidator`) is
  the production credential store; FastAPI never stores or verifies passwords for real users.
  A parallel bcrypt-based path (`IdentityService.register`/`authenticate`) exists purely for the
  fast offline test suite and non-Supabase dev — see [authentication.md](authentication.md) and
  docs/decisions.md ADR-025 for the full rationale. As of the Enterprise Security & Compliance
  milestone (2026-08), `/auth/register` and `/auth/login` are gated behind
  `TITANIQ_ENABLE_OFFLINE_AUTH` (default **off**) — this path has no email-verification
  enforcement, so a production deployment must explicitly opt in rather than have it silently
  reachable (`apps/api/routers/identity_router.py`).
- **AuthZ**: An 8-level RBAC ladder (Guest → Free → Rewarded → Premium → Moderator → Analyst →
  Administrator → Super Administrator, `modules.identity.domain.value_objects.Role`) checked at
  the API layer via `apps.api.auth_deps.require_role`, *and* enforced independently at the
  database layer via Row-Level Security (docs/decisions.md ADR-026) — defense in depth, never
  RLS-only or app-only.
- **Row-Level Security**: every table across all 11 app schemas has RLS enabled; genuinely
  user/org-owned tables carry real ownership and role-ladder policies, backend/catalog tables
  with no ownership concept are analyst+ read-only, app-facing product data (predictions,
  published news/community intelligence) is free+ read-only matching what the REST API already
  exposes to any logged-in user, and security-internal/audit tables (audit log, account lock
  state, prediction audits) have no anon/authenticated policy below administrator+ at all. Full
  per-table policy reference in [rls.md](rls.md). RLS policies are version-controlled as Alembic
  migrations (0010-0011, 0020-0022) and reviewed like code. Every schema-owning migration must
  also GRANT schema/table access to `anon`/`authenticated` (ADR-027) — missed twice already for
  schemas added after migration 0012 (`intelligence`, `predictions`), closed both times in
  ADR-049; a real recurring risk for any future schema, not a one-off fixed for good.

## 2. Secrets Management

- Provider API keys and other secrets are encrypted at rest (Supabase Vault / equivalent
  envelope encryption), never committed to the repo, never logged, never returned in plaintext
  by any API response after initial entry (Admin Center shows masked values only — see
  [admin_center.md](admin_center.md) §2).
- Environment-specific secrets injected via the deployment platform (Railway/Vercel/GitHub
  Actions secrets), not `.env` files in version control.

## 3. Application-Layer Protections

Input validation (Pydantic v2 at every API boundary) · output sanitization · CSRF protection on
any cookie-authenticated flow · explicit CORS allowlist per environment · parameterized queries
only (SQLAlchemy ORM/Core — no raw string interpolation into SQL) · XSS protection (React's
default escaping preserved, no unaudited `dangerouslySetInnerHTML`) · rate limiting per user
tier (see [api_specification.md](api_specification.md) §4).

- **Rate limiting**: `apps/api/rate_limit.py`, fixed-window counters backed by the same Redis
  instance the feature store already requires (no new dependency). `/auth/register` (5/hour by
  IP), `/auth/login` (10/min by IP), `/predictions/generate` (30/min by authenticated user). Fails
  open on a Redis outage rather than blocking real traffic on a cache being down.
- **Response headers**: `apps/api/main.py`'s `security_headers` middleware sets
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, `Strict-Transport-Security`, and a strict
  `Content-Security-Policy: default-src 'none'` on every response except FastAPI's own
  `/docs`/`/redoc` pages (which need their CDN-hosted Swagger UI assets to render).
- **Personal Access Token scopes**: `PersonalAccessToken.has_scope` is now actually enforced
  (`apps.api.auth_deps.require_scope`) rather than declared-but-unchecked — a token's scope only
  restricts the PAT/API-automation path; a Supabase-JWT-authenticated request is never
  scope-limited. Self-service tokens created via `POST /users/me/tokens` now always carry an
  expiry (default 90 days, caller-adjustable up to a 365-day cap) instead of living forever.

## 4. Auditability & Monitoring

Immutable, append-only audit trail (`identity.audit_log_entries` — no repository update/delete
method exists for it by design) records every identity/tenancy/billing security-relevant
action: registration, login success/failure, role changes, account lock/unlock, session
revocation, PAT creation/revocation, org/membership changes, subscription changes, and — as of
the Enterprise Security & Compliance milestone — **permission denials**
(`AuditAction.PERMISSION_DENIED`, emitted by `apps.api.auth_deps.require_role` whenever a
caller's role is below what a route requires; the audit write is committed independently of the
request's own transaction so it survives the 403 that follows it). Distinct from
`ingestion.timeline_events` (M5), which audits data-sync activity, not security actions. Coverage
is not yet fully unified across every subsystem (`predictions.prediction_audits` remains a
separate, structurally-incompatible free-text-actor table; no API endpoint yet exposes the raw
identity audit trail itself) — tracked as a follow-up, not fabricated as done.

Session Intelligence (`identity.sessions` — device/browser/IP tracking, concurrent-session
listing, heuristic new-IP risk scoring) and Security Intelligence (`identity.security_events`,
`identity.account_lock_states` — failed-login tracking, brute-force detection at a threshold
below account lockout so it fires as an earlier, distinct signal, account lockout after 5
consecutive failures) are both live (`modules.identity.application.identity_service`). Security
monitoring integrated with the observability stack from [architecture.md](architecture.md) §9
(OpenTelemetry traces/metrics/logs) — anomalous auth patterns and error-rate spikes are alerting
signals, not just dashboard noise.

## 5. Data Protection & Backups

Backup strategy and disaster recovery plan defined before production launch (Milestone 20 gate):
automated Postgres backups via Supabase, defined RPO/RTO targets, periodic restore drills.
Personal data handling aligned with the Privacy Policy / Data Retention Policy
(see the Legal & Responsible AI section of [titaniq.md](titaniq.md)).

## 6. Threat Model (initial, expand as subsystems land)

| Asset | Primary threats | Mitigation |
|---|---|---|
| User credentials/session | Credential stuffing, token theft | Supabase Auth, short-lived JWTs, rate limiting |
| Provider API keys | Leakage, quota abuse | Vault encryption, masked display, rotation, scoped access |
| Prediction/model IP | Scraping, unauthorized bulk extraction | Rate limiting, tiered access, ToS enforcement |
| User PII | Unauthorized access/exfiltration | RLS, least-privilege service roles, audit trail |
| Admin Center | Privilege escalation | Strict RBAC, audit log, no shared admin credentials |

## 7. Responsible AI Alignment

Security and AI governance intersect at: bias/fairness monitoring, transparency of model
decisions (explainability contract in [api_specification.md](api_specification.md) §3), and
human-gated model promotion (see [admin_center.md](admin_center.md) §3) — these are treated as
security-relevant controls, not purely product features.

## 8. Milestone Mapping

Provider Vault/masking: Milestone 3. Identity, RBAC ladder, RLS (62 tables at the time), immutable
audit trail, Personal Access Tokens, Session/Security Intelligence, Storage bucket policies,
selective Realtime: Milestone 6 (see [supabase.md](supabase.md), [rls.md](rls.md)). RLS closure
for the `intelligence`/`predictions` schemas (19 more tables, ADR-049): Milestone 9. RLS for the 7
Milestone 9.1 ML Platform tables (migrations 0023-0024, [rls.md](rls.md) §6c): ✅ applied live and
role-impersonation verified, 2026-07-26. OAuth provider
dashboard configuration (Google/GitHub live, Apple/Microsoft interface-ready) remains a manual
step — see [deployment.md](deployment.md) §Auth Provider Setup. Formal security review +
backup/DR drill: Milestone 20 gate, and before any milestone that first exposes real payment
data.

## 9. Enterprise Security & Compliance Milestone (2026-08)

A grounded architecture audit against the real codebase (not assumed from this document) found
several CRITICAL/HIGH findings that this narrative predated — full findings, attack scenarios,
and remediation status: [docs/security/phase1-audit-report.md](security/phase1-audit-report.md).
Remediated this pass: unrestricted self-service billing subscribe (C-1), role self/over-escalation
(C-2), missing admin gating on market/prediction mutation endpoints (C-3), PAT/session
revocation IDOR (H-1/H-2), rate limiting (H-3), offline-auth production gate (H-4), PAT scope
enforcement + default expiry (H-6/H-8), webhook org-membership IDOR (H-7), registration email
enumeration (M-4), permission-denial audit trail (M-2), tenancy member-list IDOR (M-8), login
IP/user-agent capture (M-7), security response headers (M-1), and RLS coverage for
watchlist/alerts (M-6). See [SECURITY_CHECKLIST.md](../SECURITY_CHECKLIST.md) for the itemized
status of every finding, including what remains open and why.
