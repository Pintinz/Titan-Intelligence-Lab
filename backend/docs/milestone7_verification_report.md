# Milestone 7 Verification Report — Squad Transfer Activity

## Objective

Extend Milestone 5's point-in-time provenance mechanism to a second structured-intelligence
source. Milestone 6 built the first consumer — Lineup Continuity — for lineups. Milestone 5's own
report named the second, still-unbuilt candidate explicitly: *"a real `VERIFIED_PRE_MATCH` signal
exists for lineups **and transfers** going forward (injuries remain honestly blocked pending a
provider with a real report timestamp)."* This milestone builds that transfer-side feature:
**Squad Transfer Activity** — a count of a team's confirmed, provenance-verified transfers within
a recent rolling window — wired into the same 14 genuinely-trained football markets Milestone 6
already established as the safe, inert wiring point.

No user-supplied M7 spec accompanied this milestone (unlike M5). Scope was determined from M1–M6
documentation and the existing implementation, per the governing instruction, and presented to the
user as an implementation plan before any code was written. Governing principles carried over
unchanged: NO DATA DUMPING. NO FABRICATION. NO DATA LEAKAGE. NO SPOOFED PROVENANCE. NO TRAINING
DURING INFERENCE. NO UNVALIDATED MODEL PROMOTION. A feature that cannot prove when its information
became available must NOT influence a prediction.

## Existing architecture reused

Nothing new was built at the infrastructure layer — this milestone is entirely new application-layer
code consuming fields/mechanisms that already existed before this milestone started:

- `Transfer.availability_classification` / `information_available_at` / `effective_date`
  (Milestone 5 — already on the domain entity and DB schema, unchanged here).
- `modules.ingestion.application.provenance.classify_availability` (Milestone 5) — confirmed by
  reading `reconcile_transfer`'s existing call site that transfers pass no
  `has_genuine_timestamp=False` override and no kickoff gate, so `VERIFIED_PRE_MATCH` is genuinely
  reachable for transfers via `SyncTrigger.LIVE_SCHEDULED` alone.
- `TransferRepositoryPort.list_by_team(team_id)` (pre-existing, unchanged) — reused directly; no
  new repository method or migration was needed.
- The `LineupContinuityCalculator` / `_LINEUP_CONTINUITY_FEATURES` pattern (Milestone 6) — this
  milestone's `TransferActivityCalculator` / `_TRANSFER_ACTIVITY_FEATURES` mirror its shape
  (dataclass calculator, `ensure_registered`/`compute_and_write`, sport-code-keyed dict on
  `EntityReconciliationService`, factory function in composition.py) so the two milestones read as
  one consistent mechanism, not two divergent ones.
- The `_ensure_aware(dt, reference)` tzinfo-normalization fix (first written for Milestone 5's own
  bug, already duplicated once in `sync_orchestrator.py` and `data_quality_engine.py`) — duplicated
  a third time locally in `windowed_feature_engineering_service.py`, the same precedented pattern,
  since SQLite drops tzinfo on read-back (ADR-007) and this calculator does its own Python-side
  datetime comparison (unlike the existing SQL-filtered calculators in that file).

## Implementation

**Feature:** `football.fixture.home_transfer_activity` / `away_transfer_activity` — for each side
of a fixture, the count of that team's transfers (incoming and outgoing) that are BOTH (a)
classified `VERIFIED_PRE_MATCH` on the transfer record itself, AND (b) have an `effective_date`
within `TRANSFER_ACTIVITY_WINDOW_DAYS` (default 30, env `TITANIQ_TRANSFER_ACTIVITY_WINDOW_DAYS`)
before the reconciliation time, strictly excluding future-dated transfers.

**Null semantics — the one piece with no direct M6 precedent.** A count of zero is genuinely
ambiguous for this feature in a way it isn't for lineup continuity: it could mean "no churn" or
"no verified visibility into this team's transfers at all." Resolved as:

- Team has **zero `VERIFIED_PRE_MATCH` transfer records on file, ever** → `None` (unavailable).
- Team has verified records, but **zero fall inside the window** → a genuine `0.0`.

This is the direct, mechanical application of the governing FINAL RULE — "any feature without
trustworthy pre-event provenance must remain unavailable/UNKNOWN rather than being fabricated" —
to a case M6 didn't need to solve (lineup continuity's `None` case is simpler: no previous lineup
record exists at all).

**Where it's computed.** Unlike a lineup, a `Transfer` record has no fixture of its own to attach
to — it affects a team's squad status across every future fixture, not one specific match. So this
calculator cannot be triggered from `reconcile_transfer` (which has no fixture context) the way
`LineupContinuityCalculator` is triggered from `reconcile_lineup` (which does, via `sync_lineups`
already loading the `Fixture`). Instead it's wired into `reconcile_fixture` directly, exactly
mirroring the existing `_compute_form_differential` helper's pattern — computed on every fixture
reconciliation, not gated on completion, "since pre-match squad state is what a prediction needs
before kickoff."

## Files changed

| File | Change |
|---|---|
| `modules/predictions/application/windowed_feature_engineering_service.py` | New `TRANSFER_ACTIVITY_WINDOW_DAYS` constant, `_ensure_aware` helper, `TransferActivityCalculator` dataclass, `football_transfer_activity_calculators()` factory |
| `modules/ingestion/application/entity_reconciliation_service.py` | New `transfer_activity_calculators: dict[str, tuple[...]]` field; new `_compute_transfer_activity` helper called from `reconcile_fixture` |
| `apps/api/composition.py` | New `build_football_transfer_activity_calculators`; wired into `build_entity_reconciliation_service` and `build_football_market_seeder` |
| `modules/predictions/football/market_seeding.py` | New `_TRANSFER_ACTIVITY_FEATURES` constant; `FootballMarketSeeder` gained a `transfer_activity_calculators` field and calls `ensure_registered()` on both in `seed()`; the same 14 trained markets' `required_features` now include both feature keys |
| `tests/unit/modules/predictions/test_windowed_feature_engineering_service.py` | 10 new tests for `TransferActivityCalculator` |
| `tests/unit/modules/predictions/test_football_market_seeding.py` | Seeder fixture updated to construct and pass transfer-activity calculators |
| `tests/unit/modules/ingestion/test_entity_reconciliation_service.py` | 3 new tests for the `reconcile_fixture` wiring |
| `docs/milestone7_verification_report.md` | This report |

## Database changes

**None.** No migration, no new column, no new table. Reuses `Transfer.availability_classification`
/ `effective_date` (Milestone 5) and the pre-existing `TransferRepositoryPort.list_by_team`
(unchanged). This was a deliberate design constraint, confirmed feasible before writing any code —
`list_by_team` already returns both incoming and outgoing transfers for a team, so windowing and
classification-filtering could be done entirely in the new application-layer calculator.

## Feature Registry changes (verified against dev.db)

Ran `scripts/seed_football_markets.py` against `dev.db` (idempotent, same script every prior
milestone's market wiring has used). Read back directly from the database afterward:

```
feature_definitions:
  football.fixture.home_transfer_activity  | status=active | leakage_classification=PRE_MATCH_SAFE | ttl=86400s
  football.fixture.away_transfer_activity  | status=active | leakage_classification=PRE_MATCH_SAFE | ttl=86400s
```

`leakage_classification=PRE_MATCH_SAFE` is set directly in `ensure_registered()`, earned because
the feature's count only ever includes transfer records that are themselves `VERIFIED_PRE_MATCH`
(§ Provenance behavior below) — the same standard Milestone 4 required for every pre-match feature.

## Feature Store changes

No schema change to the Feature Store itself. Verified live: `feature_values_offline` has **0**
rows for either `football.fixture.home_transfer_activity` or `away_transfer_activity` — this
milestone wrote nothing to the store on this run (see Production impact below for why).

## Market mappings (verified against dev.db)

```
feature_market_mappings: 28 rows (14 markets × 2 features), every row is_required=1, weight=1.0
```

The 14 mapped markets are exactly the same confirmed genuinely-trained set Milestone 6 already
targeted: `both_teams_to_score`, `total_goals_over_under` (+ `_0_5`/`_1_5`/`_3_5`/`_4_5`),
`home_team_total_goals`, `away_team_total_goals`, `home_clean_sheet`, `away_clean_sheet`,
`home_win_to_nil`, `away_win_to_nil`, `correct_score`, `match_winner`. The 4 heuristic-placeholder
markets present in the `MARKETS` tuple (`first_half_winner`, `second_half_winner`,
`first_half_goals`, `first_half_both_teams_to_score`) correctly have no transfer-activity mapping —
same reasoning as Milestone 6: those markets read `FeatureMarketMapping` live at inference time via
the heuristic-formula fallback, so adding a feature there would be a live behavior change to
already-serving predictions, not inert prep.

`required_features` changing is confirmed inert for the 14 trained markets' currently-serving
Champions, for the identical reason established (and re-verified by re-reading
`PredictionEngine._resolve_predictor`) in Milestone 6: a trained Champion consumes its own
persisted `feature_order` captured at training time — `required_features` only takes effect on that
market's *next* retrain.

## Provenance behavior

The count strictly requires, per candidate transfer record:

1. `availability_classification == "VERIFIED_PRE_MATCH"` on the transfer record itself (set only
   by `classify_availability` when the record was synced via `SyncTrigger.LIVE_SCHEDULED` and
   passed validation — the exact same choke point Milestone 5 built and Milestone 6 already
   depends on).
2. `effective_date` inside `[now - TRANSFER_ACTIVITY_WINDOW_DAYS, now)` — the lower bound is
   inclusive (a transfer dated exactly at the window boundary counts), the upper bound is
   exclusive and strict (`effective_date < now`), so a transfer dated at or after the
   reconciliation instant — not yet in effect — never counts as already-happened churn.

A transfer synced via `SyncTrigger.MANUAL`/`ADMIN_MANUAL`/`BACKFILL` lands as
`UNKNOWN_AVAILABILITY_TIME` at the reconciliation layer (unchanged Milestone 5 behavior — this
milestone adds no new trigger-handling logic) and is therefore excluded by condition 1 above,
regardless of how recent its `effective_date` is. This was directly tested (see Tests added).

## Leakage analysis

| Risk | Mitigation |
|---|---|
| Counting `UNKNOWN`/`POST_MATCH`/`EXPIRED`/`INVALID`-classified transfers as verified churn | Hard filter on `== "VERIFIED_PRE_MATCH"` per record, tested against all four other classifications |
| Treating "0 verified in window" as "0 churn" when it really means "no verified data at all" | Two-case null semantics (§ Implementation) — a team with zero verified records ever returns `None`, not `0.0` |
| A future-dated `effective_date` (not yet in effect) counting as current churn | Strict `< now` upper bound, tested explicitly including an exactly-`now` edge case |
| Naive/aware datetime comparison crash (Milestone 5's exact prior bug, in a different call site) | Same `_ensure_aware` fix applied here, since this calculator does its own Python-side comparison unlike the SQL-filtered existing calculators |
| `required_features` change silently altering a live-serving Champion's behavior | Confirmed inert — re-verified against `PredictionEngine._resolve_predictor`, same proof Milestone 6 already established |
| Retroactively reclassifying or backfilling existing `UNKNOWN` transfer records to make the feature "work" | Never attempted — 0/308 existing transfers were touched; verified live against `dev.db` (see Production impact) |

## Tests added

`tests/unit/modules/predictions/test_windowed_feature_engineering_service.py` — 10 tests:

- `test_transfer_activity_counts_verified_transfers_within_window` — pre-match eligibility
- `test_transfer_activity_excludes_unknown_availability_transfers` — manual/backfill exclusion +
  unknown-timestamp exclusion (both scenarios collapse to the same `UNKNOWN_AVAILABILITY_TIME`
  classification at the reconciliation layer)
- `test_transfer_activity_excludes_non_verified_pre_match_classifications` — post-match exclusion,
  plus `EXPIRED`/`INVALID` (the strict `==` filter, not merely "not UNKNOWN")
- `test_transfer_activity_returns_none_when_no_verified_transfers_exist_at_all` — the "unavailable,
  not fabricated" null case
- `test_transfer_activity_returns_genuine_zero_when_verified_history_exists_outside_window` — the
  genuine-zero null case, distinct from the one above
- `test_transfer_activity_excludes_future_dated_transfers` — historical leakage prevention
- `test_transfer_activity_window_boundary_is_inclusive_of_start_exclusive_of_now` — boundary precision
- `test_transfer_activity_home_and_away_use_distinct_feature_keys_and_team_filters` — home/away
  correctness
- `test_transfer_activity_ensure_registered_sets_pre_match_safe_leakage_classification` — feature
  registration
- `test_transfer_activity_ensure_registered_is_idempotent`

`tests/unit/modules/ingestion/test_entity_reconciliation_service.py` — 3 tests:

- `test_reconcile_fixture_computes_transfer_activity_for_both_sides` — fixture association +
  home/away correctness at the reconciliation-wiring level (calculator called once per side, with
  the correct `fixture_id`/`team_id`)
- `test_reconcile_fixture_skips_transfer_activity_without_sport_code`
- `test_reconcile_fixture_skips_transfer_activity_for_unregistered_sport`

`tests/unit/modules/predictions/test_football_market_seeding.py` — the existing
`test_seed_maps_every_declared_required_feature` test (and others) now exercise the
transfer-activity wiring too, since it asserts against `MARKETS`' own `required_features`
dynamically rather than a hardcoded feature list — market mapping is covered without a separate
new test.

## Full test results

- `tests/unit/modules/predictions/test_windowed_feature_engineering_service.py`: 34 passed
  (10 new).
- `tests/unit/modules/ingestion/test_entity_reconciliation_service.py`: 56 passed (3 new).
- `tests/unit/modules/predictions/test_football_market_seeding.py`: 9 passed.
- Full backend suite (`pytest -q`, run from `backend/`): **2020 passed, 58 skipped**, 0 failed,
  1263.42s.

## Regression comparison against M6

| | M6 baseline | M7 result | Delta |
|---|---|---|---|
| Passed | 2007 | 2020 | +13 (exactly the new tests added: 10 + 3) |
| Skipped | 58 | 58 | 0 |
| Failed | 0 | 0 | 0 |

No regressions. The skip count is unchanged — the pre-existing Redis-dependent/integration skips
in this environment, unrelated to this milestone.

## Known limitations

- **Injuries remain unaddressed**, unchanged from Milestone 5/6 — no provider adapter supplies a
  real report timestamp for injuries (`ApiFootballAdapter.fetch_injuries` uses `fixture.date`, i.e.
  kickoff, not a report time), so `has_genuine_timestamp=False` stays hardcoded and injuries can
  never reach `VERIFIED_PRE_MATCH` today. Not attempted here — would require a new provider
  capability, not application-layer work.
- **`TRANSFER_ACTIVITY_WINDOW_DAYS=30` is a configured default, not a fitted value** — no real
  outcome history exists yet to calibrate against, same "honest v1, no fitted model" posture
  documented for `LINEUP_PREMATCH_WINDOW_MINUTES` and `NEW_STAT_FEATURE_WEIGHTS`.
- **The 5 heuristic-placeholder markets still don't consume this feature** — same deliberate
  exclusion Milestone 6 already established, for the same reason (live behavior change vs. inert
  prep). Remains a candidate for a future, separately-approved milestone.

## Remaining blockers

None specific to this milestone's own scope. The feature is fully implemented, registered, mapped,
and tested. What remains blocked is unchanged from Milestone 5/6's own findings:

- No retrain has been triggered — `required_features` changing is prep only, per the standing
  "no training/promotion" rule this session has honored since Milestone 4.
- The feature has never been observed with a real non-null value in `dev.db` (see Production
  impact) — nothing in this milestone can be live-verified against a real prediction until the
  `sync-upcoming-structured-intelligence-football-epl` Celery Beat task genuinely runs against a
  fixture inside its window and produces at least one `VERIFIED_PRE_MATCH` transfer record — the
  same open item Milestone 5's report already flagged as "not yet observed live."

## Production impact

**None today — purely inert prep work**, verified live against `dev.db`:

```
transfers total=308, verified=0
feature_values_offline rows for football.fixture.{home,away}_transfer_activity: 0
```

Zero of the 308 real transfer records currently in `dev.db` qualify as `VERIFIED_PRE_MATCH` (same
finding Milestone 5/6 already recorded for lineups — nothing in the local dataset has ever been
synced via the `LIVE_SCHEDULED` trigger). Re-running the market seeder does not retroactively
compute or backfill this feature for any existing record — `compute_and_write` is only ever called
from inside `reconcile_fixture` at reconciliation time, and no historical-data backfill script
calls it. `required_features` now lists the two new feature keys for 14 markets' *next* retrain,
but zero feature values exist anywhere in the store, and zero currently-serving predictions
changed.

## Rollback procedure

Purely additive — no migration, no schema change, no data mutation performed (0/308 transfer
records were reclassified). To roll back:

1. Revert the diff (the 7 changed files listed above).
2. No database rollback is needed — nothing was written to `feature_values_offline`, and the two
   `feature_definitions`/28 `feature_market_mappings` rows created by re-running
   `scripts/seed_football_markets.py` are themselves harmless to leave in place (an unused,
   correctly-classified feature definition with no consumer), but can be deleted with:
   ```sql
   DELETE FROM feature_market_mappings WHERE feature_key LIKE '%transfer_activity%';
   DELETE FROM feature_definitions WHERE feature_key LIKE '%transfer_activity%';
   ```
3. No Celery Beat schedule, admin endpoint, or API contract was touched — rollback has no
   operational surface beyond the code diff and the two optional SQL statements above.

## Acceptance checklist

- [x] Feature counted only from transfer records genuinely classified `VERIFIED_PRE_MATCH` —
      never from unknown/manual/backfill/post-match provenance.
- [x] `information_available_at <= event_start_time` semantics preserved — no fabricated
      timestamps; a feature without trustworthy pre-event provenance returns `None`, not a
      fabricated value.
- [x] No hand-picked/fabricated weight — a pure count (§ Implementation).
- [x] Two independent home/away features, not an assumed-symmetric differential.
- [x] Genuine-zero vs. no-verified-data-at-all null semantics correctly distinguished and tested.
- [x] `leakage_classification=PRE_MATCH_SAFE` set correctly, verified against `dev.db`.
- [x] Wired only into the 14 confirmed genuinely-trained markets' `required_features`, verified
      against `dev.db`; the 5 heuristic markets correctly untouched.
- [x] `required_features` change confirmed inert for already-serving Champions.
- [x] Historical-data safety verified live: 0/308 transfers reclassified, 0 feature values
      backfilled retroactively.
- [x] No database migration, no schema change — reused existing Milestone 5 fields and the
      pre-existing `TransferRepositoryPort.list_by_team`.
- [x] 13 new unit/integration tests; full backend suite green with no regressions against the M6
      baseline (2020 passed vs. 2007, +13 exactly, 58 skipped unchanged, 0 failed).
- [x] No training, retraining, or model promotion triggered by this milestone.
- [x] M1–M6 documentation and existing implementation read before any code was written; an
      implementation plan was presented to the user before implementation began.

## Stop condition

Per the standing process and the explicit instruction governing this milestone, this report is the
stop point. **Do not automatically begin Milestone 8** — wait for explicit approval before
proceeding.
