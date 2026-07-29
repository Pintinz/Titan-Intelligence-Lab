# TitanIQ — Row Level Security Reference

Status: Live on the `titaniq` Supabase project as of migrations 0010-0024. Every table across
all 11 app schemas (96 tables, including `predictions` and `intelligence` as of the Milestone 9
RLS closure pass, and the 7 Milestone 9.1 ML Platform tables, §6c) has RLS enabled; every policy
below is real, applied, and hand-verified against the live project (see docs/decisions.md
ADR-026/027/049, and the automated `tests/integration/test_rls.py` suite for the durable,
repeatable version of that verification). Migrations 0023-0024 applied and role-impersonation
verified live (anon/authenticated/moderator correctly denied, analyst/service-role correctly
permitted) on 2026-07-26 — see §6c.

**Milestone 9 RLS closure pass** (migrations 0020-0022): the `predictions` schema (Milestone 9)
and `intelligence` schema (Milestone 8) went live without either the GRANT prerequisite
(ADR-027) or RLS policies — both schemas were added after migration 0012 shipped and neither was
folded back into it. Migration 0020 extends 0012's GRANT pattern to both; 0021/0022 add the RLS
policies documented in §6a/§6b below. Closed as a single pass rather than two separate ones
since the root cause (a new schema-owning migration forgetting the GRANT step) and the fix
shape are identical for both.

FastAPI connects via the service-role, which bypasses RLS entirely — RLS here is defense in
depth against any direct-to-Postgres/PostgREST/Realtime/Supabase-client access, not the primary
authorization mechanism (that's `apps.api.auth_deps.require_role` + the application services).

## 1. The RBAC ladder

`modules.identity.domain.value_objects.Role`, mirrored in SQL by `identity.role_level(text)`:

| Level | Role | Level | Role |
|---|---|---|---|
| 0 | Guest (unauthenticated / `anon`) | 4 | Moderator |
| 1 | Free | 5 | Analyst |
| 2 | Rewarded | 6 | Administrator |
| 3 | Premium | 7 | Super Administrator |

`identity.has_role_at_least(min_role text)` compares the caller's current role (looked up from
`identity.users` via `auth.uid()`, `SECURITY DEFINER` so the lookup itself isn't blocked by
RLS) against that threshold. **One policy per threshold covers every role above it** — a
`has_role_at_least('moderator')` policy is satisfied by Moderator, Analyst, Administrator, and
Super Administrator alike. Free/Rewarded/Premium get identical database-level access to their
own data; the distinction between those three tiers is enforced by
`modules.billing.application.billing_service` at the application layer, not by RLS.

Every elevated-read policy below is **read-only**. No role gets a write path through RLS —
writes always go through FastAPI's service-role connection, so there is exactly one audited
mutation path per table (docs/decisions.md ADR-026).

## 2. `identity` schema

| Table | Own-row access | Elevated access |
|---|---|---|
| `users` | SELECT own row | SELECT any row: moderator+ |
| `profiles` | SELECT/INSERT/UPDATE own row | SELECT any row: moderator+ |
| `federated_identities` | SELECT/DELETE own rows | SELECT any row: administrator+ |
| `personal_access_tokens` | SELECT/DELETE own rows | SELECT any row: administrator+ |
| `sessions` | SELECT/DELETE own rows | SELECT any row: moderator+ |
| `security_events` | none | SELECT: moderator+ only |
| `account_lock_states` | none | SELECT: moderator+ only |
| `audit_log_entries` | none | SELECT: administrator+ only |

`security_events`/`account_lock_states`/`audit_log_entries` have **no self-access policy at
all** — a regular user cannot see their own failed-login history or audit trail via RLS, only
via a FastAPI admin-gated endpoint if one is ever built. These are security-internal by design.

## 3. `tenancy` schema

| Table | Access |
|---|---|
| `organizations` | SELECT if member (`is_org_member`) or administrator+; INSERT if you're the named owner; UPDATE/DELETE if owner/admin member (`is_org_admin`) or administrator+ (SELECT only) |
| `teams` | SELECT if org member; write (ALL) if org owner/admin; SELECT any: administrator+ |
| `memberships` | SELECT if org member (see the whole roster); write if org owner/admin; SELECT any: administrator+ |
| `invitations` | SELECT if org admin **or** the invitee's own email (`auth.jwt() ->> 'email'`); write if org owner/admin; SELECT any: administrator+ |

`tenancy.is_org_member(org_id)` / `tenancy.is_org_admin(org_id)` are `SECURITY DEFINER` helpers
(same rationale as the identity-schema ones) that check `tenancy.memberships` without being
blocked by that table's own RLS when called from another table's policy.

## 4. `billing` schema

| Table | Access |
|---|---|
| `plans` | SELECT: public (`anon` + `authenticated`) — pricing-page catalog data |
| `entitlements` | SELECT: public — "this plan includes X" |
| `subscriptions` | SELECT own (user) or org's (if member); SELECT any: analyst+ |
| `usage_counters` | SELECT own or org's; SELECT any: analyst+ |

No write policies on any billing table — subscriptions/usage are managed exclusively by
`BillingService` through the service-role connection.

## 5. `webhooks` schema

| Table | Access |
|---|---|
| `webhook_endpoints` | Org owner/admin only (ALL); SELECT any: administrator+ |
| `webhook_deliveries` | SELECT if org owner/admin of the parent endpoint; SELECT any: administrator+ |

## 6. `sports` / `admin` / `features` / `ingestion` / `knowledge_graph` (M2-M5, 44 tables)

No per-user ownership concept — populated by the ingestion pipeline, read by FastAPI. One
policy per table: `SELECT USING (identity.has_role_at_least('analyst'))`. No write policies —
Free/Premium/Moderator get **zero** direct access (they never need it; the API surfaces this
data through prediction/analytics endpoints, out of scope until later milestones).
`sports.alembic_version` is the one exception — pure schema bookkeeping, service-role-only, no
analyst+ policy.

## 6a. `predictions` (Milestone 9, migration 0021, 8 tables)

Three tiers, chosen by what each table actually is — not a blanket analyst+ like §6, because
`predictions`/`prediction_markets` genuinely are product data an ordinary app user reads (via
`/api/v1/predictions`/`/api/v1/markets`, `get_current_user`-gated, no role check):

| Table | Access |
|---|---|
| `prediction_markets` | SELECT: free+ (any real authenticated user, unfiltered by status) |
| `predictions` | SELECT: free+ (unfiltered) |
| `feature_market_mappings` | SELECT: analyst+ only — Feature-to-Market Registry, not app-facing |
| `models` | SELECT: analyst+ only — Champion/Challenger registry, not app-facing |
| `prediction_outcomes` | SELECT: analyst+ only |
| `model_evaluations` | SELECT: analyst+ only |
| `experiments` | SELECT: analyst+ only |
| `prediction_audits` | SELECT: **administrator+ only** — mirrors `identity.audit_log_entries` (§2), not analyst+, because it's an audit trail (who did what), not analytics data |

No write policies on any table — Champion selection, Model publishing, Rollback, registry
modification, and prediction administration all continue exclusively through FastAPI's
service-role connection (`apps.api.routers.prediction_admin_router`, `Role.ADMINISTRATOR`-gated
at the application layer). `prediction_audits`/`prediction_outcomes`/`model_evaluations`/
`experiments` have no UPDATE/DELETE policy at all, so they are append-only from every RLS-visible
role's perspective, including administrator.

## 6b. `intelligence` (Milestone 8, migration 0022, 11 tables)

Two tiers, mirroring `apps/api/routers/intelligence_router.py`'s actual `get_current_user`
(any authenticated user, no role check) posture for the tables it directly serves — not
inventing a stricter model than the API itself already uses:

| Table | Access |
|---|---|
| `news_articles`, `news_events`, `community_topics`, `sentiment_results`, `impact_scores`, `summaries`, `source_reliability_scores` | SELECT: free+ — every one of these is returned by an `intelligence_router.py` route |
| `news_sources` | SELECT: analyst+ only — never returned directly, only referenced by `id` from inside an article row |
| `community_posts` | SELECT: analyst+ only — `community/topics` reads `community_topics`, not raw posts |
| `intelligence_sync_runs`, `intelligence_sync_checkpoints` | SELECT: analyst+ only — pure ingestion bookkeeping, same shape as `ingestion.sync_runs` (§6) |

No write policies — News/Community ingestion, extraction, and enrichment continue exclusively
through the service-role connection.

## 6c. `predictions` ML Platform tables (Milestone 9.1, migrations 0023-0024, 7 tables — ✅ live)

One tier — analyst+, matching the existing Model Registry tables' shape (§6a): none of these 7
are read directly by an app user (no `/api/v1/*` route serves them unfiltered the way
`predictions`/`prediction_markets` are).

| Table | Access |
|---|---|
| `datasets`, `training_runs`, `calibration_reports`, `feature_importance_reports`, `latency_samples`, `retraining_jobs`, `model_artifacts` | SELECT: analyst+ only |

No write policies — Dataset building, training, calibration reporting, latency recording, and
artifact registration all continue exclusively through FastAPI's service-role connection. GRANT
was already covered by migration 0020's `ALTER DEFAULT PRIVILEGES IN SCHEMA predictions` — these
7 tables, created in that schema after 0020 ran, automatically inherited the anon/authenticated
GRANT with no extra migration step, closing the ADR-027 gap-recurrence pattern (ADR-049)
proactively for this schema — confirmed live: security advisor reported zero new findings after
migrations 0023-0024, and role-impersonation hand-verification (anon, authenticated with no role
row, moderator — all correctly denied; analyst, service-role — correctly permitted) passed
against the live project on 2026-07-26, transaction rolled back, zero residual test data.
A full FK-graph round-trip (market → model → dataset → training_run → calibration_report/
feature_importance_report/model_artifact, plus latency_samples/retraining_jobs) and the
`uq_dataset_market_version` unique constraint were also verified live in the same rolled-back
transaction. One real gap found and fixed during verification: `training_runs.dataset_id`'s
foreign key had no covering index (Supabase performance advisor) — added live
(`ix_predictions_training_runs_dataset_id`) and folded back into migration 0023's source so a
fresh deployment includes it from the start.

## 7. Storage (`storage.objects`)

Same ownership-path convention as the database tables, applied to object keys:
`{bucket}/{owner_id}/filename`, checked via `(storage.foldername(name))[1] = auth.uid()::text`.

| Bucket | Public read? | Write |
|---|---|---|
| `avatars` | Yes | Owner (INSERT/UPDATE/DELETE); moderator+ can also DELETE (content moderation) |
| `team-logos`, `competition-logos` | Yes | administrator+ only |
| `ai-reports`, `generated-charts`, `uploads`, `temporary-files` | No — owner SELECT only | Owner (INSERT/DELETE); administrator+ SELECT (support) |

## 8. Realtime

12 of 96 tables are in the `supabase_realtime` publication: 8 from migration 0014 (`sports.matches`,
`sports.match_events`, `admin.provider_health_state`, `admin.provider_incidents`,
`ingestion.sync_runs`, `identity.sessions`, `identity.security_events`,
`webhooks.webhook_deliveries`) plus 4 more from migration 0019 (`predictions.predictions`,
`predictions.prediction_markets`, `predictions.prediction_audits`,
`features.feature_values_offline`) — see docs/decisions.md ADR-028 for the migration-0014
per-table rationale. Broadcasts still respect each subscriber's own RLS, so this list adds no
data exposure beyond what a one-shot SELECT already allows that subscriber.

## 9. Verifying a policy change

1. Generate offline SQL for the new migration: `alembic upgrade <prev>:<new> --sql` against a
   dummy `postgresql+asyncpg://` URL (no real credentials needed — the dialect is what matters).
2. Strip Alembic's interleaved `INFO [alembic.runtime.migration]` log lines before treating the
   output as executable SQL.
3. Apply via the Supabase MCP's `execute_sql` (never `apply_migration` — see ADR-024).
4. Run `tests/integration/test_rls.py` against the live project (`TITANIQ_INTEGRATION_DB_URL`
   set) — it impersonates each role via `SET LOCAL ROLE` + `request.jwt.claims` inside a
   transaction that's always rolled back, so no test data ever persists.
