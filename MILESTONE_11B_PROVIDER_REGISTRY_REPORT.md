# Milestone 11B — Enterprise Provider Registry & Operations Integration

## 0. Scope correction (read this first)

The brief assumed the backend had no Provider Registry — that credentials were still
environment-variable-only, and that the whole system (encryption, health monitoring, usage
tracking, RBAC, audit) needed to be built from scratch. Investigation before writing any code
found that was **not accurate**: `backend/modules/admin/` already had a complete, tested Provider
Management System since Milestone 3 — Fernet-encrypted multi-credential storage, register/
activate/deactivate/rotate, quota tracking with exhaustion prediction, per-provider circuit
breaking, and a full `HealthIntelligenceEngine` (reliability scoring, incident tracking,
automatic recovery detection). `docs/admin_center.md` documented this as "Implementation status:
... all built and tested." `GET /api/v1/admin/providers` returning `[]` wasn't a stub; it was a
real, working, repository-backed endpoint with zero rows in the table because nothing had ever
been registered.

This was confirmed with the user before writing code (see conversation), who approved building
the *real* gap instead of a redundant rebuild: the missing piece was that **no endpoint or UI
action could ever create a provider, add a credential, or delete one** — the service layer could
do all of it, nothing exposed it. That gap, plus the genuinely-missing pieces (usage/history/
category aggregation reads, a real connection tester, the Celery health-check job the docs
explicitly deferred, and audit logging for provider actions), is what this milestone built.

The brief's ".env fallback" instruction was also deliberately not implemented literally, per the
same pre-code discussion — see §5.

---

## 1. Architecture summary

No new module was created; this milestone extends the existing `modules/admin/` hexagonal module
(domain/application/infrastructure/ports) rather than duplicating it:

- **Domain** (`domain/entities.py`, `domain/value_objects.py`): `ProviderDefinition` grew 12 new
  fields (base URL, auth type, region, version, environment, timeout/retry policy, created_by/
  updated_by, created_at/updated_at). `ProviderCategory` grew from 2 values to 5
  (`sports_data`/`ai`/`news`/`odds`/`general`).
- **Application** (`application/provider_management_service.py`): added `update_provider`,
  `delete_provider`, `masked_credentials`, `import_from_env`, and the `mask_credential` helper.
  New shared orchestration module `application/connection_check_service.py` — the one place both
  the manual "Test Connection" endpoint and the Celery health-check job run the same probe-and-
  record logic, so they can't drift apart.
- **Infrastructure**: new `infrastructure/connection_tester.py` (provider-agnostic HTTP prober)
  and `infrastructure/celery/tasks.py` (the periodic health-check job). `infrastructure/
  persistence/{models,mappers,repositories}.py` extended for the new fields and a `delete`
  repository method.
- **Ports** (`ports/repositories.py`): added `ProviderRepositoryPort.delete` and
  `UsageRepositoryPort.list_by_provider`.
- **API** (`apps/api/main.py`): 13 new routes under `/api/v1/admin/providers`, all
  `Role.ADMINISTRATOR`-gated identically to every existing admin route, all audit-logged through
  `identity.audit_log_entries` (the same table/mechanism role changes already use — extended
  `AuditAction` with 8 new `PROVIDER_*` values rather than inventing a second audit system).

## 2. Completed capabilities

- Register / update / delete a provider (full field set, not just key/name/category/priority).
- Activate / disable (disable was previously service-only — `deactivate()` existed, nothing
  called it).
- Add / list (masked) / rotate credentials.
- Real connection testing — an actual HTTP request to the provider's `base_url`, not a manually
  asserted `{success: true}` the way the old "Test Connection" button worked.
- One-time `.env` → registry import (see §5).
- Real usage, history, category, and status aggregation reads.
- Periodic background health checks via Celery beat (previously reserved but unwired).
- Audit trail for every mutating provider action.

## 3. Backend-integrated / real vs. what's still honest-gap

Everything above is real and tested against a live database — no `BackendPendingState`
placeholders were needed for this milestone, because the milestone's job was specifically to
close the gaps that would have required one. Two things worth naming as deliberately unbuilt:

- **Provider failover automation** — the brief asked for automatic priority-based failover
  (offline/auth-failure/timeout/rate-limit triggers a switch to the next-priority provider of the
  same category). `priority` is a real, settable field and `SportsProviderRouter` already tries
  providers by priority for the sports category specifically — but a cross-category, connection-
  test-driven automatic failover engine is a genuinely new piece of runtime logic, not a gap-fill,
  and wasn't attempted this pass.
- **Notifications** (quota-low, repeated-errors, recovery alerts) — the existing Alerts &
  Monitoring page (Milestone 11A) already surfaces prediction alerts and provider incidents
  honestly; a dedicated provider-quota notification channel would be new scope, not wired here.

## 4. New endpoints

All under `/api/v1/admin/providers`, `Role.ADMINISTRATOR`-gated:

| Method | Path | Purpose |
|---|---|---|
| POST | `/providers` | Register |
| GET | `/providers/{id}` | Fetch one |
| PATCH | `/providers/{id}` | Patch-style update |
| DELETE | `/providers/{id}` | Delete (cascades credentials/usage/health/incidents) |
| POST | `/providers/{id}/disable` | Deactivate |
| GET / POST | `/providers/{id}/credentials` | List (masked) / add |
| POST | `/providers/{id}/rotate-key` | Rotate |
| POST | `/providers/{id}/test`, `/refresh` | Real connection test + record |
| POST | `/providers/import-from-env` | One-time `.env` migration |
| GET | `/providers/{id}/usage` | Real quota/usage numbers |
| GET | `/providers/{id}/history` | Merged health checks + incidents |
| GET | `/providers/categories`, `/providers/status` | Aggregate counts |

(`/activate` and the health-intelligence dashboard routes already existed from Milestone 3.)

## 5. Environment variable migration — the deliberate deviation from the brief

The brief asked for "read from DB; if unavailable, fall back to `.env`; log the fallback." That
is not what got built, and this was discussed with the user before writing code. The existing,
already-shipped design (`SportsProviderRouter._resolve_adapter`) doesn't have an env fallback at
all today — no usable DB credential means the *mock* adapter is used ("active provider, no key
yet — dev mode"), never a raw `os.environ` read. Adding a standing env-read path would create a
second, permanent credential channel that bypasses the encrypted vault entirely — a real security
regression, not a neutral compatibility shim.

Instead, `POST /providers/import-from-env` reads a named environment variable **exactly once**,
encrypts it into the vault, and registers/credentials the provider. From that request onward it's
indistinguishable from a credential entered by hand — the DB is the only source of truth, nothing
keeps re-reading the environment on subsequent requests.

## 6. Connection testing

`modules/admin/infrastructure/connection_tester.py` — deliberately provider-agnostic. One HTTP
GET to `base_url` with the credential attached per `auth_type` (`bearer` / `api_key_header` /
`api_key_query` / `basic`); classifies the transport-level outcome into exactly the vocabulary the
brief asked for: healthy / warning / offline / unauthorized / rate_limited / timeout /
not_configured. It never parses a provider's response body — that's what keeps one implementation
working for every current and future provider category (sports, news, AI, odds, general) without
per-provider code, matching "support both current and future providers."

Verified live against a real external endpoint (httpbin.org) during this milestone's testing —
not just unit-tested against a mock transport.

## 7. Background health monitoring

`modules/admin/infrastructure/celery/tasks.py`'s `admin.check_all_provider_health` task runs the
same connection-test-and-record logic as the manual buttons, for every `ACTIVE` provider, on the
`PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS` (300s) cadence `beat_schedule.py` had reserved since
Milestone 5 but never wired up. Uses the existing Celery app and factory-injection pattern
(`set_admin_context_factory`) already established by the ingestion module's tasks — no new job
infrastructure introduced.

## 8. Database migration

`alembic/versions/0025_provider_registry_fields.py` — additive columns on `admin.providers`
(nullable or defaulted, zero impact on existing rows/queries), plus switching the `admin.*`
foreign keys to `ON DELETE CASCADE` (Postgres-guarded; SQLite test fixtures get the same behavior
directly from `models.py`) so `DELETE /providers/{id}` can remove a provider's full history in one
call. Applied and verified against the real local dev database (`backend/dev.db`) in addition to
the migration file itself.

## 9. Two more real bugs found via full-suite regression testing

Running the entire backend suite (not just the admin-scoped subset) surfaced two genuine issues,
both fixed:

- **Shared cache leak across test files**: `get_vault_settings()` (`vault.py`) is a process-
  lifetime `@lru_cache`. `test_api_admin_providers.py`'s fixture set its own encryption key via
  `monkeypatch.setenv` — correct in isolation, but in a full-suite run it's one of the earliest
  tests to warm that cache, and the cached key then silently applied to later, unrelated tests in
  `webhooks`/`tenancy` that expected their own. Fixed by calling `get_vault_settings.cache_clear()`
  in the fixture's teardown. Confirmed by running the full suite three times: with the new test
  files included (5 unrelated files failed), with them excluded (0 unrelated failures), and again
  with them included plus this fix (0 failures) — isolating the exact cause rather than guessing.
- **New Celery task never registered for its own validation test**: `test_beat_schedule_entries_
  reference_registered_task_names` imports `modules.ingestion.infrastructure.celery.tasks` to
  register Celery's task decorators before checking every `BEAT_SCHEDULE` entry has a matching
  registered task — it didn't import the new `modules.admin.infrastructure.celery.tasks`, so my
  `admin.check_all_provider_health` entry failed the check. Fixed by adding the same import the
  test already does for ingestion's tasks.

Final full-repo suite after both fixes: **1397 passed, 0 failed, 58 skipped** (skips are
pre-existing, e.g. tests gated on optional ML dependencies).

## 11. A real bug found and fixed during endpoint testing

While writing endpoint tests, `POST .../activate` and `PATCH .../{id}` crashed with SQLAlchemy's
`MissingGreenlet` error — a genuine, pre-existing bug in `SqlAlchemyProviderRepository.upsert()`,
never caught before because no endpoint test had ever exercised `activate`/`deactivate` through a
real HTTP+database round trip (only through in-memory fake repositories). Root cause: `updated_at`
uses `onupdate=func.now()`; after an UPDATE, SQLAlchemy expires that attribute, and reading it
immediately (as the new domain-mapping code now does, to expose `updated_at` in the API) triggered
an implicit, un-awaited lazy-reload. Fixed with an explicit `await self.session.refresh(model)`
after flush, with a comment explaining why it's there. Verified via an isolated, FastAPI-free
repro before and after the fix to confirm the exact mechanism, not just that tests went green.

## 10. Testing

- 18 service-layer unit tests (`test_provider_management_service.py`) — including the 7 that
  predate this milestone, all still passing — covering registration with the new fields, update
  semantics, delete, credential masking, and all three `.env`-import paths (success, reuse
  existing provider, missing var).
- 10 connection-tester unit tests (`test_connection_tester.py`) — every status classification
  (200/401/429/500/timeout/connection-error), auth-header/query-param wiring, and confirmation
  that a credential value never appears in any returned message.
- 19 endpoint tests (`test_api_admin_providers.py`) — RBAC, full CRUD, activate/disable,
  credentials/rotation, `.env` import (success + 422), connection test, usage/history/categories/
  status, and a direct audit-log assertion.
- **Full repository test suite: 1397 passed, 0 failed, 58 skipped** (final run, after fixing the
  two full-suite-only issues in §9) — every module in the backend, not just the ones this
  milestone touched.

## 12. Security

- No endpoint ever returns a plaintext credential — `mask_credential()` computes the masked
  display value server-side from a controlled decrypt-then-discard; the plaintext never leaves
  the function.
- No log line or exception message contains a credential value (asserted directly in the
  connection-tester tests).
- RBAC unchanged: every new route uses the exact same `require_role(Role.ADMINISTRATOR)`
  dependency as every pre-existing admin route — no new permission tier invented.
- Every mutating action is audit-logged with actor, action, target, timestamp, IP address, and a
  metadata diff — verified via a direct database read in the endpoint tests, not just "the
  endpoint returned 200."

## 13. Frontend

Per the brief's own instruction, Provider Management was **not redesigned** — the existing page
(`frontend/src/pages/ops/provider-management.tsx`, built in Milestone 11A) keeps its layout,
expand/collapse card pattern, and health/trend/incidents/diagnostics panels untouched. What was
added, using the same visual language already established (`SectionCard`, `Button`, `Input`,
`Select`, `KeyValueGrid`):

- A "Register a provider" form (key/name/category/base URL) plus an inline "Import from .env"
  action, replacing the empty state's dead end.
- Disable button (previously only Activate existed) and a Delete button with a confirmation
  prompt.
- A credentials panel per provider — masked list, add-credential form, inline rotate.
- A usage panel per provider (requests today, quota, remaining, success rate).
- "Test connection" now calls the real backend probe and shows the real classification/message
  via toast, instead of unconditionally recording a fake `{success: true}`.

`lib/api/admin-platform.ts` gained 14 new methods; `lib/api/types.ts` gained proper `ProviderDto`/
`ProviderCredentialMaskedDto`/`ConnectionTestResultDto`/etc. interfaces (previously `listProviders`
returned an untyped inline shape). `lib/api/client.ts` gained a `patch` method (only `get`/`post`/
`delete` existed).

## 14. Verification performed

- `tsc --noEmit` — clean.
- `npm run build` — succeeds, no new warnings.
- Impeccable mechanical detector on `provider-management.tsx` — zero findings.
- **Backend: 1397/1397 passing, full repository suite** (§10), including three full-suite runs
  used specifically to isolate and confirm the two cross-test-file issues in §9 were real and
  fixed, not assumed.
- **Live verification against the running local backend** (not just tests): registered a real
  provider, added a real credential, ran a real HTTP connection test against httpbin.org (got back
  `"status": "healthy"`, real latency, real HTTP 200), confirmed masked-credential display never
  contains the plaintext, confirmed category/status aggregates update correctly, confirmed
  activate/audit-log writes with real IP addresses via direct database read, and confirmed delete
  cascades cleanly (no FK violation — provider and its credential both gone afterward, confirmed
  via a follow-up 404). The `backend/dev.db` SQLite file was migrated with the same additive
  columns migration `0025` adds, so this was a genuine end-to-end round trip against the same
  database the running dev server actually uses, not a mocked one. Test data was cleaned up
  afterward (`GET /providers` confirmed empty again).
- A live browser click-through of the updated Provider Management UI was in progress when the
  browser's Supabase session expired (unrelated to this work — a session timeout, not caused by
  the backend restart). The curl-level verification above is comprehensive enough that this wasn't
  blocking, but a screenshot pass can follow on request if you sign back in.

## 15. Additive backend endpoint recommendations for future milestones

None — this milestone's job was specifically to stop needing this section for Provider
Management. The two deliberately-unbuilt pieces from §3 (failover automation, provider-specific
notifications) are the honest remaining gap, not additive-endpoint requests.
