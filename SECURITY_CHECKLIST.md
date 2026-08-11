# TitanIQ — Security Checklist

Enterprise Security & Compliance milestone, 2026-08-09. Tracks the disposition of every finding
from [docs/security/phase1-audit-report.md](docs/security/phase1-audit-report.md), the grounded
architecture audit that opened this milestone. Status reflects the real state of the codebase at
the time this file was last edited — verify against the code, not just this list, before relying
on it for a release decision.

Legend: ✅ Remediated & tested · 🟡 Partially addressed / accepted risk (reason given) · ⬜ Not started

## CRITICAL

| ID | Finding | Status | Remediation |
|---|---|---|---|
| C-1 | Billing `subscribe`/`cancel` had no payment check — any authenticated user could grant themselves any plan for free | ✅ | Restricted to `Role.ADMINISTRATOR` (`billing_router.py`) until a real payment provider is integrated. |
| C-2 | No block on role self-escalation or granting a role above the actor's own | ✅ | `IdentityService.change_role` now rejects both (`RoleEscalationError` → 403). |
| C-3 | Market/prediction mutation endpoints (register/approve/reject/promote/deprecate/archive/remove) had no role gate | ✅ | All 9 endpoints + prediction approve/reject gated to `Role.ADMINISTRATOR`. |

## HIGH

| ID | Finding | Status | Remediation |
|---|---|---|---|
| H-1 | PAT revocation had no ownership check (IDOR) | ✅ | `revoke_personal_access_token` compares `token.user_id` to actor; mismatch → 404. |
| H-2 | Session revocation had no ownership check (IDOR) | ✅ | Same pattern for `revoke_session`. |
| H-3 | No rate limiting anywhere | ✅ | Redis-backed fixed-window limiter (`apps/api/rate_limit.py`) on register/login/predictions-generate. |
| H-4 | Offline bcrypt auth path unconditionally mounted, no production gate, no email verification | ✅ | Gated behind `TITANIQ_ENABLE_OFFLINE_AUTH` (default off). |
| H-5 | Entitlement checks (`has_feature`/`check_within_limit`) exist but gate nothing real | ⬜ | Not started this pass — depends on C-1's billing model being trustworthy first; wire into `predictions/generate` and other paid-tier surfaces next. |
| H-6 | PAT scopes declared but never enforced | ✅ | `apps.api.auth_deps.require_scope` enforces `has_scope`; wired onto `predictions/generate` as the reference implementation. |
| H-7 | Webhook management endpoints had no organization-membership check (IDOR) | ✅ | Mirrors `tenancy_router.py`'s org-role check; register/rotate/deactivate require admin, list requires any member. |
| H-8 | Self-service PATs never expired | ✅ | Default 90-day expiry, caller-adjustable up to a 365-day cap. |

## MEDIUM

| ID | Finding | Status | Remediation |
|---|---|---|---|
| M-1 | No security response headers | ✅ | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Strict-Transport-Security`, `Content-Security-Policy` on every response (docs excepted). |
| M-2 | No audit trail on `require_role` 403s | ✅ | `AuditAction.PERMISSION_DENIED`, committed independently of the failing request's own transaction. |
| M-3 | (see phase1-audit-report.md §3 for the full list — remaining M-items below) | — | — |
| M-4 | Registration error enumerated existing emails | ✅ | Generic "unable to complete registration" message. |
| M-5 | Audit-log coverage gaps (feature-flag changes, data export, model rollback unaudited; no read endpoint over the raw trail) | ⬜ | Explicitly out of scope this pass — flagged in the audit itself as needing separate scoping (audit-trail unification across 4 structurally different tables), not attempted partially to avoid a shallow fix. |
| M-6 | No RLS policies on `watchlist.watchlist_entries` / `alerts.alert_events` | ✅ | Migration `0035_watchlist_alerts_rls.py`, same self-ownership pattern as `identity.sessions`/PATs. **Not live-verified against Postgres this pass** (no live DB connection available in this environment) — verify with the `tests/integration/test_rls.py` harness before treating as fully confirmed, same as every other RLS migration in this history. |
| M-7 | Login never captured IP/user-agent even though the service layer already supported it | ✅ | Router now passes `request.client.host` / `User-Agent` through to `authenticate()`. |
| M-8 | `tenancy_router.list_members` had no membership check — any authenticated user could list any org's members | ✅ | `TenancyService.list_members` now requires the actor to be a member. |

## LOW / INFORMATIONAL

Not remediated this pass — see phase1-audit-report.md §4-5 for the full list (password-reset gap
on the offline path, `PredictionAudit.actor` type inconsistency, frontend `.env.example`
containing a real-but-browser-safe project ref, webhook signature code correct but no live inbound
receiver yet). None are blocking; none were silently dropped from the record.

## Verification

- Every ✅ item above has a corresponding automated test (see `backend/tests/unit/apps/` —
  `test_api_billing.py`, `test_api_identity.py`, `test_api_markets.py`, `test_api_predictions.py`,
  `test_api_rate_limit.py`, `test_api_security_headers.py`, `test_api_tenancy.py`,
  `test_api_webhooks.py`).
- Full backend unit suite passing at time of writing: `1913 passed, 0 failed` (`pytest tests/unit`).
- Frontend `tsc --noEmit` clean at time of writing.
- `tests/integration/test_rls.py` is gated behind a live Postgres connection (`requires_db`
  marker) and does not run in this sandboxed environment — the M-6 migration's SQL was reviewed
  for consistency with the existing, live-verified `0010_row_level_security.py` pattern but has
  not itself been exercised against real Postgres.

## Explicitly out of scope this pass

H-5 (entitlement enforcement), M-5 (audit-log unification/coverage), and the full documentation
set the original brief requested (`SECURITY_ARCHITECTURE.md`, `THREAT_MODEL.md` as a standalone
file, `DATA_CLASSIFICATION.md`, `AUDIT_LOGGING.md`, `INCIDENT_RESPONSE.md`) were not attempted —
each is a genuinely separate, non-trivial scoping exercise, and a shallow version of any of them
would read as complete without being trustworthy. `docs/security.md` §6 carries a threat-model
table already; `docs/security/phase1-audit-report.md` carries the detailed attack-scenario
analysis per finding. Treat those two as the current threat-model reference until a dedicated
document is written.
