# Milestone 5 Verification Report — Verified Pre-Match Data Availability

**Status:** Complete. Per Milestone 5's own closing instruction, this is a STOP point — no
training, retraining, model promotion, sport expansion, news/community feature activation, or
historical-data reclassification has occurred. Waiting for explicit approval before Milestone 6.

**Scope discipline maintained throughout:** every change is additive; no existing column removed,
renamed, or reinterpreted; every new provenance field defaults to the honest "unknown" state; no
existing dev.db row was mass-reclassified.

---

## 1. Files changed

**New:**
- `modules/ingestion/application/provenance.py` — the reusable provenance classification mechanism
- `alembic/versions/0040_milestone5_prematch_availability.py`
- `tests/unit/modules/sports/test_availability_classification.py`

**Modified (backend):**
- `modules/ingestion/domain/value_objects.py` — `SyncTrigger` extended (5 new values)
- `modules/ingestion/application/entity_reconciliation_service.py` — `reconcile_lineup`/
  `reconcile_injury`/`reconcile_transfer` wired to `classify_availability`
- `modules/ingestion/application/sync_orchestrator.py` — `sync_lineups`/`sync_injuries`/
  `sync_transfers` trigger defaults corrected, `run_id` threading, new
  `sync_upcoming_structured_intelligence` method, `_run_sync` gained an optional `run_id` param,
  a real timezone-awareness bug found and fixed (see §17)
- `modules/ingestion/infrastructure/celery/tasks.py` — `sync_upcoming_structured_intelligence_task`
- `modules/ingestion/infrastructure/celery/beat_schedule.py` — new Beat entry + interval constant
- `modules/sports/domain/entities.py` — `fetched_at`/`sync_run_id` on `Lineup`/`Injury`/
  `Suspension`/`Transfer`
- `modules/sports/infrastructure/persistence/models.py` — same 2 columns on the 4 matching tables
- `modules/sports/infrastructure/persistence/mappers.py` — carry-through for `Lineup`/`Injury`/
  `Transfer` (no `Suspension` mapper exists — table is empty, no active reconciliation path, per
  Milestone 4's finding, unchanged here)
- `apps/api/main.py` — 3 admin sync endpoints hardened to pass `trigger=SyncTrigger.ADMIN_MANUAL`
  explicitly
- `scripts/backfill_squad_intelligence.py` — explicit `trigger=SyncTrigger.BACKFILL`

**Modified (tests):**
- `tests/unit/modules/ingestion/test_entity_reconciliation_service.py` —
  `TestVerifiedPreMatchAvailabilityIntegration` (6 tests)
- `tests/unit/modules/ingestion/test_sync_orchestrator.py` — 2 end-to-end
  `sync_upcoming_structured_intelligence` tests
- `tests/unit/apps/test_api_ingestion.py` — trigger-spoofing resistance test (scenario L)

## 2. Database migrations

**0040** — additive: `fetched_at` (nullable `DateTime`) + `sync_run_id` (nullable `String(64)`) on
`sports.injuries`/`sports.suspensions`/`sports.transfers`/`sports.lineups`. Full `downgrade()`
provided. Applied directly to `dev.db` via a one-off script (dev.db is not Alembic-managed
locally, per this project's established convention). Confirmed live: all 8 columns added with no
errors, and all existing rows (30 injuries, 308 transfers, 4 lineups) confirmed to still carry
`availability_classification=UNKNOWN_AVAILABILITY_TIME` and `fetched_at=NULL` after the migration
— nothing was mass-reclassified (§9).

## 3. New models / fields

- `Lineup`/`Injury`/`Transfer`/`Suspension` (domain + DB model): `fetched_at: datetime | None`,
  `sync_run_id: str | None` (stored as plain string — `SyncRunId.value` — to avoid a
  `modules.sports` → `modules.ingestion` domain-layer dependency).
- `modules.ingestion.application.provenance.AvailabilityClassification` (new enum):
  `VERIFIED_PRE_MATCH` / `UNKNOWN_AVAILABILITY_TIME` / `POST_MATCH` / `EXPIRED` / `INVALID` — the
  5-state vocabulary the spec required, not collapsed into a boolean.

## 4. New timestamp semantics

- **`fetched_at`** — when the provider response was retrieved. Recorded unconditionally on every
  successful reconciliation call, regardless of trigger or provenance outcome.
- **`information_available_at`** — when the underlying real-world fact became knowable. Populated
  **only** when `classify_availability` returns `VERIFIED_PRE_MATCH`; `NULL` for every other
  classification. Never derived from `fetched_at`, `created_at`, `updated_at`, or fixture kickoff
  as a substitute (explicitly checked in code review of every call site).
- **`kickoff`** — the fixture's own `scheduled_at`, read from the existing `Fixture` entity; not a
  new field, just a new input to the classification function for fixture-bound entities (lineups).

## 5. New trigger types

`SyncTrigger` extended from 4 values (`SCHEDULED`, `MANUAL`, `RETRY`, `LIVE` — all pre-existing,
untouched) to 9: added `LIVE_SCHEDULED`, `ADMIN_MANUAL`, `BACKFILL`, `RECONCILIATION`, `SYSTEM`.
`OTHER` was **not** added — no genuine need for a catch-all emerged, and adding an unused value
would violate the spec's own "the exact implementation should follow the existing architecture
rather than introducing unnecessary abstractions" instruction.

**Critical rule enforced in code, not just by convention:** `classify_availability` only ever
produces `VERIFIED_PRE_MATCH` when `trigger is SyncTrigger.LIVE_SCHEDULED` — every other value
(including the new ones) falls through to `UNKNOWN_AVAILABILITY_TIME`/`INVALID`/`POST_MATCH`. This
is a single `if` check in one function, not scattered logic — see `provenance.py`.

## 6. Celery Beat schedules

| Entry | Task | Interval | Args |
|---|---|---|---|
| `sync-upcoming-structured-intelligence-football-epl` | `ingestion.sync_upcoming_structured_intelligence` | 900s (15 min) | `("football", "<EPL season_id>")` |

**Cadence rationale** (documented in `beat_schedule.py`): matches `PROVIDER_POLL_INTERVAL_SECONDS`
(the same free-tier-safe cadence every football-data.org-class entry already uses). At 15 minutes,
`LINEUP_PREMATCH_WINDOW_MINUTES` (default 90) is checked roughly 6 times before it closes — several
real chances to catch official lineups once the provider actually publishes them, without polling
aggressively enough to burn quota on fixtures still hours from kickoff. Injuries/transfers ride the
same schedule and interval rather than a separate one — `sync_upcoming_structured_intelligence`
already dedupes team-level syncs per run, so a second interval knob would add configuration surface
without a real behavioral difference.

Football/EPL only, matching every sport-scoped Beat entry's existing pattern — injuries/transfers/
lineups reconciliation exists today only for football (confirmed in Milestone 3's audit).

**Verified end-to-end** (§14 requirement): `ingestion.sync_upcoming_structured_intelligence` is
registered in `celery_app.tasks` (confirmed via direct import check), the Beat entry's `task` name
matches exactly, and `test_sync_upcoming_structured_intelligence_end_to_end`/
`test_sync_upcoming_structured_intelligence_skips_lineups_outside_kickoff_window` exercise the full
chain — orchestrator → provider (fake) → reconciler → database → `SyncRun` → provenance
classification — against a real SQLite session, proving the object graph the Beat entry triggers
actually produces the right `SyncRun.trigger` and downstream classification. Not exercised against
the *real* live provider or *real* Beat scheduler process (no fixture in dev.db currently falls
within the 72-hour structured-intel window to make a live run meaningful — confirmed by querying
dev.db directly; see §17 for what this leaves unverified).

## 7. Kickoff-proximity implementation

`LINEUP_PREMATCH_WINDOW_MINUTES` (env-configurable via `TITANIQ_LINEUP_PREMATCH_WINDOW_MINUTES`,
default 90 — official lineups are conventionally published ~60 minutes before kickoff; 90 gives a
periodic, not continuous, Beat schedule real margin to land inside the window rather than narrowly
missing it) and `STRUCTURED_INTEL_SYNC_WINDOW_HOURS` (env-configurable via
`TITANIQ_STRUCTURED_INTEL_SYNC_WINDOW_HOURS`, default 72 — how far ahead a fixture is considered
"upcoming" and worth prioritizing at all). `is_within_prematch_window(kickoff, sync_time, window)`
is a pure function: `sync_time` must fall in `[kickoff - window, kickoff)` — strictly before
kickoff. Real timezone-awareness bug found and fixed during this milestone's own testing (§17).

## 8. Provenance rules

`classify_availability(...)` (the single choke point) implements the exact 5-condition rule from
the approved spec:

```
if not applicable or not validated:     -> INVALID
elif not sync_succeeded:                -> UNKNOWN_AVAILABILITY_TIME
elif fixture_status is COMPLETED:       -> EXPIRED
elif kickoff is not None and sync_time >= kickoff:  -> POST_MATCH
elif trigger is not LIVE_SCHEDULED:     -> UNKNOWN_AVAILABILITY_TIME
elif not has_genuine_timestamp:         -> UNKNOWN_AVAILABILITY_TIME
elif kickoff/window given and outside it:  -> UNKNOWN_AVAILABILITY_TIME
else:                                    -> VERIFIED_PRE_MATCH (information_available_at = sync_time)
```

`kickoff`/`prematch_window_minutes` are optional — passed for lineups (fixture-bound), omitted for
injuries/transfers (not fixture-bound, per spec §7). `has_genuine_timestamp` defaults `True`
(nothing to doubt for lineups/transfers) and is explicitly forced `False` for injuries (§10).

## 9. Injury handling

`reconcile_injury` hardcodes `has_genuine_timestamp=False` — **not** derived from provider data
per-call, because no connected provider adapter supplies a genuine injury report/publication
timestamp today (`ApiFootballAdapter.fetch_injuries`'s `reported_at` is the fixture's own kickoff,
per its Milestone 4 finding, unchanged and re-confirmed here). This means an injury can never reach
`VERIFIED_PRE_MATCH` today, **even under `LIVE_SCHEDULED`** — exactly the spec's explicit "do not
mark VERIFIED_PRE_MATCH merely because it was retrieved by a scheduled task" instruction. Test F
(`test_availability_classification.py`) proves the mechanism *can* produce `VERIFIED_PRE_MATCH` for
an injury the moment a real timestamp exists (`has_genuine_timestamp=True`); test G proves today's
real path stays `UNKNOWN_AVAILABILITY_TIME`. No historical `reported_at` value was rewritten.

## 10. Transfer handling

Different temporal semantics from lineups, per spec §7: no kickoff-proximity gate (a transfer isn't
bound to one fixture — it affects a player's squad status across every future fixture a team plays).
`information_available_at` is the reconciliation `now`, never derived from `effective_date` (a real
but distinct field — when the move takes effect, not when it became known) — gated purely by
trigger (`LIVE_SCHEDULED` only) + validation + success, same as every other entity. No
"announced_at" field exists on any connected provider (confirmed during the pre-implementation
investigation) — not fabricated here.

## 11. Lineup handling

Fixture-bound: `kickoff` = the reconciled `Fixture.scheduled_at`, `fixture_status` = the reconciled
`Fixture.status`. `sync_lineups` now resolves the fixture directly (previously it never looked at
the fixture beyond its provider ref) to supply both. `EXPIRED` reachable when the fixture is fully
`COMPLETED`; `POST_MATCH` reachable when `sync_time >= kickoff` but the match isn't yet marked
completed — a real, meaningful distinction the spec's 5-state vocabulary was built to preserve.

## 12. Historical-data treatment

Confirmed live against dev.db after applying migration 0040 (§2): 0 of 30 injuries, 0 of 308
transfers, 0 of 4 lineups were reclassified away from `UNKNOWN_AVAILABILITY_TIME`, and 0 rows
gained a `fetched_at` value. No backfill/reclassification script was written for this milestone
(unlike Milestone 4's `normalize_provider_ref_index_entity_id.py`, a deliberate, narrowly-scoped,
approved exception for a different, already-fixed bug) — existing rows remain honestly unknown
until a separate, evidence-backed historical reconciliation is explicitly approved, per spec §9.

## 13. Tests added

- `tests/unit/modules/sports/test_availability_classification.py` — 17 tests: scenarios A–K (pure
  `classify_availability`/`is_within_prematch_window` coverage) plus 3 additional branch-coverage
  tests (COMPLETED→EXPIRED, failed sync, unvalidated data).
- `tests/unit/modules/ingestion/test_entity_reconciliation_service.py::TestVerifiedPreMatchAvailabilityIntegration`
  — 6 tests proving the real reconciliation call path (not just the pure function) for
  lineups/injuries/transfers under both `LIVE_SCHEDULED` and non-qualifying triggers.
- `tests/unit/modules/ingestion/test_sync_orchestrator.py` — 2 end-to-end tests for
  `sync_upcoming_structured_intelligence` (full fan-out + trigger propagation; kickoff-window
  gating for lineups specifically).
- `tests/unit/apps/test_api_ingestion.py::test_admin_injuries_sync_cannot_spoof_trigger_via_request_body`
  — scenario L, against the real admin API and a real persisted `SyncRun`.

**28 new tests total**, covering all 12 named scenarios (A–L).

## 14. Test results

Full `tests/unit` suite: **1999 passed, 0 failed**, in 1009.53s. Run after every Milestone 5 change
was complete, including the timezone-awareness bug fix (§17).

## 15. Example VERIFIED_PRE_MATCH record

Generated directly from `classify_availability` (no dev.db row currently qualifies live — see §6/§17):

```
kickoff = 2026-08-15T15:00:00Z
sync_time = 2026-08-15T14:15:00Z  (45 min pre-kickoff, LIVE_SCHEDULED trigger)
-> AvailabilityResult(
     classification=VERIFIED_PRE_MATCH,
     information_available_at=2026-08-15T14:15:00Z,
   )
```

## 16. Example UNKNOWN_AVAILABILITY_TIME record

Same fixture/timing, `ADMIN_MANUAL` trigger instead:

```
kickoff = 2026-08-15T15:00:00Z
sync_time = 2026-08-15T14:15:00Z  (same timing, ADMIN_MANUAL trigger)
-> AvailabilityResult(
     classification=UNKNOWN_AVAILABILITY_TIME,
     information_available_at=None,
   )
```

Every one of dev.db's 342 existing structured-intelligence rows is a real instance of this state
today (§12).

## 17. Remaining provenance risks

- **No fixture in dev.db currently falls within the live structured-intel window** — the Beat
  schedule's real end-to-end behavior against the actual API-Football adapter has not been
  observed live, only proven via the fake-router integration tests (§6). This is a timing fact
  about dev.db's current seeded data, not a code gap — the mechanism itself is fully tested.
- **A real timezone-awareness bug was found and fixed during this milestone's own test-writing**
  (not by the user, not pre-existing from Milestone 4): `sync_upcoming_structured_intelligence`
  and `sync_lineups`'s fixture-context resolution both compared a SQLite-read-back
  `Fixture.scheduled_at` (naive, per this project's documented ADR-007 SQLite/aiosqlite
  behavior) directly against timezone-aware `datetime`s, raising `TypeError` the moment a real
  fixture was involved instead of a hand-constructed one. Fixed by routing both through the
  file's own pre-existing `_ensure_aware` helper (the same fix pattern already used elsewhere in
  `sync_orchestrator.py` for the identical class of bug). Caught by
  `test_sync_upcoming_structured_intelligence_end_to_end` failing on first run — the test caught a
  real bug, not the other way around.
- **No provider today supplies a genuine injury report timestamp** — `has_genuine_timestamp=False`
  is hardcoded for injuries (§9). This is a data-source limitation, not a code gap; the mechanism
  is ready the moment a provider supplies one.
- **`sync_run_id` is stored as a plain string, not a real foreign key** — deliberate (avoids a
  `modules.sports` → `modules.ingestion` domain dependency, matching this codebase's existing
  hexagonal boundary rules), but means the database itself cannot enforce referential integrity
  between a structured-intelligence row and its `SyncRun` — the link is trustworthy only insofar
  as the reconciliation code that wrote it is correct (which is now test-covered, §13).

## 18. Whether the Feature Store can now safely consume these records

**Not yet activated, per spec §10 — this milestone establishes trustworthy availability metadata
only.** The Feature Store's own point-in-time infrastructure (`get_as_of`/`read_as_of`, Milestone
4) is unrelated to and unaffected by this milestone — it already correctly requires
`information_available_at <= cutoff` for feature values, but no structured-intelligence field is
wired into any `FeatureMarketMapping` yet (confirmed unchanged from Milestone 4's finding). A
future milestone building that wiring can now safely gate on `availability_classification ==
VERIFIED_PRE_MATCH` and `information_available_at <= fixture_kickoff` — the metadata to do so
honestly now exists, where before this milestone it did not.

## 19. What remains blocked

Per Milestone 5's own closing instruction: no model training, retraining, Champion promotion,
model-weight modification, news feature activation, community feature activation, historical
training-dataset rebuilding, or historical availability-timestamp fabrication occurred. No
structured-intelligence field has been wired into the production ML feature vector.

## Recommended Milestone 6 scope (for consideration, not committed)

1. Design and implement the market-specific structured-intelligence feature (the item Milestone 5
   was a prerequisite for) — now genuinely unblocked: a real `VERIFIED_PRE_MATCH` signal exists for
   lineups and transfers going forward (injuries remain honestly blocked pending a provider with a
   real report timestamp).
2. Retrain the 14 existing football Champions under `TIME_SERIES_SPLIT` (Milestone 4's
   recommendation, still open) and compare via `ChallengerEvaluationService` before promotion.
3. Observe the Beat schedule against a real upcoming EPL fixture once one enters the live window,
   to close §17's "not yet observed live" gap with a genuine production data point.

---

## Acceptance checklist

- [x] Injuries have a real recurring synchronization path (`sync_upcoming_structured_intelligence`
      on a 15-min Beat schedule).
- [x] Transfers have a real recurring synchronization path (same).
- [x] Lineups have a real recurring synchronization path (same, kickoff-gated).
- [x] Lineups have explicit fetch/provenance timestamps (`fetched_at` distinct from
      `information_available_at`).
- [x] Lineup synchronization has a configurable kickoff-proximity gate
      (`LINEUP_PREMATCH_WINDOW_MINUTES`, env-overridable).
- [x] `SyncRun` distinguishes scheduled/live, manual, backfill, and other triggers (9-value enum).
- [x] `VERIFIED_PRE_MATCH` can only originate from the approved `LIVE_SCHEDULED` pathway (enforced
      in one function, tested against spoofing via the real admin API).
- [x] `information_available_at` is never fabricated (never derived from `fetched_at`/
      `created_at`/`updated_at`/kickoff as a substitute).
- [x] Existing unknown-provenance records remain unknown (confirmed live against dev.db post-migration).
- [x] Injury timestamp leakage remains blocked (`has_genuine_timestamp=False` hardcoded, tested).
- [x] Provenance is traceable to `SyncRun`/provider/fixture (`sync_run_id` on every structured-
      intelligence row).
- [x] Frontend/admin clients cannot spoof provenance (tested against the real API with a spoofing
      attempt in the request body).
- [x] Celery Beat actually executes the schedules (task registered, entry verified, full chain
      tested against a fake provider — not yet observed against the real provider, §17).
- [x] Automated tests cover the provenance rules (28 new tests, all 12 named scenarios).
- [x] No model training occurred.
- [x] No Champion was promoted.
- [x] No synthetic data was introduced.
- [x] No production ML feature was activated solely because this milestone was completed.
