# Milestone 6 Verification Report — Lineup Continuity: The First Structured-Intelligence Feature

## 0. Scope and governing rule

Milestone 5 built the mechanism for knowing *whether* structured intelligence (lineups,
injuries, transfers) was genuinely available before kickoff. Milestone 6 is the first real
consumer of that mechanism: a feature that only computes when the lineup backing it is
`VERIFIED_PRE_MATCH`, and that is wired — safely, inertly — into the required-feature set of
every market that can actually use it today.

No spec message accompanied this milestone; scope was drawn from the Milestone 5 report's own
"Recommended Milestone 6 scope" section (item 1), and explained to the user before work began.
Governing principles carried over unchanged: NO DATA DUMPING. NO FABRICATION. NO DATA LEAKAGE.
NO SPOOFED PROVENANCE. NO TRAINING DURING INFERENCE. NO UNVALIDATED MODEL PROMOTION. EVERY
PRE-MATCH FEATURE MUST HAVE TRACEABLE AVAILABILITY.

## 1. What was built

**Lineup Continuity** — for each team in a fixture, the fraction of that team's previous
confirmed starting eleven that starts again:

```
|current_starters ∩ previous_starters| / |previous_starters|
```

Two independent features per fixture (`football.fixture.home_lineup_continuity` /
`football.fixture.away_lineup_continuity`), not a single differential — a team's own lineup
rotation affects only its own output; nothing about this signal is symmetric between the two
sides, so collapsing it into `home - away` (the shape `FixtureFormDifferentialCalculator` uses)
would assume a relationship that doesn't exist here. This matches
`FixtureExpectedGoalsCalculator`'s existing independent-home/away-value shape instead.

A pure ratio with no hand-picked weight, continuing this codebase's established convention
(confirmed by reading `market_seeding.py`'s own incident note: an unweighted stat differential
saturated a sigmoid to ~99.9% confidence on 2026-08-06 — hand-picked weights on raw-scale
features are the specific failure mode being avoided here; a 0..1 ratio needs no weight to stay
in range).

## 2. Why this feature, and why now

Milestone 4's Champion-provenance trace found 14 of football's 19 markets are genuinely
trained models; the other 5 (`first_half_winner`, `second_half_winner`, `first_half_goals`,
`first_half_both_teams_to_score`, plus the absent `match_result`) are heuristic placeholders
served by a live formula predictor. Investigation (an Explore pass over the prediction engine)
established a load-bearing fact before any code was written:

> `required_features` only affects a **trained** model's *next retrain* — it does not
> retroactively change what an already-serving Champion consumes, because a trained Champion
> uses its own persisted `feature_order` captured at training time
> (`PredictionEngine._resolve_predictor` only reads `FeatureMarketMapping` live for the
> heuristic-formula fallback path).

This makes wiring the new feature into the 14 trained markets' `required_features` **safely
inert** — it changes nothing about what any currently-serving prediction consumes, and only
takes effect the next time each market is genuinely retrained on real outcome history. Wiring it
into the 5 heuristic markets, by contrast, would be a **live behavior change** to
already-serving predictions today — explicitly out of scope here, and flagged as a deliberate
follow-up, not an oversight.

## 3. Files changed

| File | Change |
|---|---|
| `modules/sports/ports/repositories.py` | Added `LineupRepositoryPort.list_recent_by_team(team_id, before, limit=10) -> list[Lineup]` |
| `modules/sports/infrastructure/persistence/repositories.py` | Implemented `list_recent_by_team` on `SqlAlchemyLineupRepository` — joins `Lineup → Match → Fixture` for `scheduled_at` (a `Lineup` carries no date of its own) |
| `modules/predictions/application/windowed_feature_engineering_service.py` | New `LineupContinuityCalculator` dataclass + `football_lineup_continuity_calculators()` factory |
| `modules/ingestion/application/entity_reconciliation_service.py` | `EntityReconciliationService` gained a `lineup_continuity_calculators: dict[str, tuple[...]]` field (sport-code-keyed); `reconcile_lineup` gained `fixture_id`, `home_team_id`, `sport_code` kwargs and calls the correct-side calculator right after persisting a lineup |
| `modules/ingestion/application/sync_orchestrator.py` | `sync_lineups`'s `reconcile_lineup` call now passes `fixture_id`, `home_team_id`, `sport_code` (it already fetches the `Fixture` for Milestone 5's kickoff-proximity gate) |
| `apps/api/composition.py` | New `build_football_lineup_continuity_calculators(session)`; `build_entity_reconciliation_service` now wires it in for `sport_code="football"`; `build_football_market_seeder` now passes it to `FootballMarketSeeder` |
| `modules/predictions/football/market_seeding.py` | New `_LINEUP_CONTINUITY_FEATURES` constant; `FootballMarketSeeder` gained a `lineup_continuity_calculators` field and calls `ensure_registered()` on both in `seed()`; the 14 trained markets' `required_features` now include both feature keys |
| `tests/unit/modules/predictions/test_windowed_feature_engineering_service.py` | 9 new tests for `LineupContinuityCalculator` |
| `tests/unit/modules/predictions/test_football_market_seeding.py` | Seeder fixture updated to construct and pass lineup-continuity calculators |
| `docs/milestone6_verification_report.md` | This report |

No domain entities, database schema, or migrations changed — this milestone consumes fields
Milestone 5 already added (`Lineup.availability_classification`, `information_available_at`).

## 4. A design flaw caught before any test ran

The first `LineupContinuityCalculator` wiring paired home/away calculators as a flat tuple,
assuming the caller could trivially tell which side a `team_id` belongs to. But
`EntityReconciliationService.reconcile_lineup` only ever received a `match_id`, not the
`Fixture` — it had no way to determine home/away, or even which sport, without more context.
Caught by re-reading the call site before writing any test, not by a failing assertion. Fixed
by:

- Adding `fixture_id: str | None`, `home_team_id: TeamId | None`, `sport_code: str | None` to
  `reconcile_lineup`, populated by `sync_lineups` (which already loads the `Fixture` for
  Milestone 5's kickoff-proximity gate — no new fetch required).
- Changing `lineup_continuity_calculators` from a flat `(home, away)` tuple to
  `dict[str, tuple[LineupContinuityCalculator, LineupContinuityCalculator]]` keyed by sport
  code — mirroring the existing `form_differential_calculators` field's shape — so a future
  non-football sport's calculators can never be silently misapplied to a football lineup.

## 5. Feature registration and market wiring (verified against dev.db)

Ran `scripts/seed_football_markets.py` against `dev.db` (idempotent — same script every prior
milestone's market wiring already used). Read back directly from the database afterward:

```
feature_definitions:
  football.fixture.home_lineup_continuity  | status=active | leakage_classification=PRE_MATCH_SAFE | ttl=86400s
  football.fixture.away_lineup_continuity  | status=active | leakage_classification=PRE_MATCH_SAFE | ttl=86400s

feature_market_mappings: 28 rows (14 markets × 2 features), every row is_required=1, weight=1.0
```

The 14 mapped markets are exactly the confirmed genuinely-trained set from Milestone 4:
`both_teams_to_score`, `total_goals_over_under` (+ `_0_5`/`_1_5`/`_3_5`/`_4_5`),
`home_team_total_goals`, `away_team_total_goals`, `home_clean_sheet`, `away_clean_sheet`,
`home_win_to_nil`, `away_win_to_nil`, `correct_score`, `match_winner`. The 4 heuristic markets
present in the `MARKETS` tuple (`first_half_winner`, `second_half_winner`, `first_half_goals`,
`first_half_both_teams_to_score`) correctly have no lineup-continuity mapping.

`leakage_classification=PRE_MATCH_SAFE` is set directly in `ensure_registered()` right after
registration — earned because the feature is only ever written from a lineup that already
carries `VERIFIED_PRE_MATCH` (see §6), the same guarantee Milestone 4 required for every
pre-match feature.

## 6. Point-in-time safety

`LineupContinuityCalculator.compute_and_write` refuses to write unless the lineup just
reconciled is itself `VERIFIED_PRE_MATCH`:

```python
if lineup.availability_classification != "VERIFIED_PRE_MATCH":
    return None
```

The comparison baseline — the team's *previous* lineup — does not need the same guarantee: it's
an already-settled historical fact by the time the current fixture is being predicted, not
something that could leak the current fixture's own outcome. The baseline lookup is bounded by
`lineup.information_available_at` (falling back to `now` only if that's unset), not by `now`
directly — a dedicated test (`test_lineup_continuity_only_looks_before_information_available_at_not_now`)
proves a lineup for a *later* fixture, reconciled before this write happens in wall-clock time,
cannot leak into the baseline for an earlier one.

## 7. Historical-data safety (verified against dev.db)

```
Lineups with availability_classification = 'VERIFIED_PRE_MATCH': 0
feature_values_offline rows for football.fixture.{home,away}_lineup_continuity: 0
```

Zero existing lineups in `dev.db` currently qualify as `VERIFIED_PRE_MATCH` (same finding
Milestone 5's report already recorded — no lineup in the local dataset was ever synced via the
`LIVE_SCHEDULED` trigger, the only trigger that can produce that classification). Re-running the
market seeder does not retroactively compute or backfill this feature for any existing record —
`compute_and_write` is only ever called from inside `reconcile_lineup` at sync time, and no
historical-data backfill script calls it. This milestone is, today, purely inert prep work:
`required_features` now lists the two feature keys for 14 markets' *next* retrain, but zero
feature values exist anywhere in the store yet, and zero currently-serving predictions changed.

## 8. Tests added

`tests/unit/modules/predictions/test_windowed_feature_engineering_service.py` — 9 tests:

- `test_lineup_continuity_computes_overlap_ratio_with_previous_starters` — 3-of-4 overlap → 0.75
- `test_lineup_continuity_uses_away_feature_key_for_the_away_calculator`
- `test_lineup_continuity_returns_none_when_current_lineup_is_not_verified_pre_match`
- `test_lineup_continuity_returns_none_when_no_previous_lineup_exists`
- `test_lineup_continuity_returns_none_when_previous_lineup_has_no_starters`
- `test_lineup_continuity_only_looks_before_information_available_at_not_now` — the leakage-
  boundary test described in §6
- `test_lineup_continuity_ensure_registered_sets_pre_match_safe_leakage_classification`
- `test_lineup_continuity_ensure_registered_is_idempotent`

`tests/unit/modules/predictions/test_football_market_seeding.py` — existing seeder tests
(`test_seed_maps_every_declared_required_feature` and others) now exercise the lineup-continuity
wiring too, since they assert against `MARKETS`' own `required_features` dynamically rather than
a hardcoded feature list — no separate new test needed there to prove the 14-market mapping is
correct end-to-end.

## 9. Test results

- `tests/unit/modules/predictions` + `tests/unit/modules/ingestion` + `tests/unit/modules/sports`
  + `tests/unit/apps`: **1384 passed**, 0 failed.
- Full backend suite (`pytest -q`, run from `backend/`): **2007 passed, 58 skipped**, 0 failed,
  664.83s. Skips are the pre-existing Redis-dependent/integration tests this repo already skips
  in this environment — unrelated to this milestone.

## 10. What remains blocked / deliberately deferred

- **The 5 heuristic-placeholder markets** (`first_half_winner`, `second_half_winner`,
  `first_half_goals`, `first_half_both_teams_to_score`, and the unregistered `match_result`) do
  not consume this feature. Wiring them would be a live behavior change to currently-serving
  predictions and needs its own dedicated verification pass, not a byproduct of this milestone.
- **No retrain has been triggered.** `required_features` changing is prep only — the 14 trained
  markets' live Champions are unaffected until each is genuinely retrained on real outcome
  history, per §2.
- **The feature has never been observed with a real non-null value.** Zero lineups in `dev.db`
  have ever reached `VERIFIED_PRE_MATCH` (§7) — this is a Milestone 5 finding, not new here.
  Nothing in this milestone can be live-verified against a real prediction until the
  `sync-upcoming-structured-intelligence-football-epl` Celery Beat task genuinely runs against a
  fixture inside its kickoff-proximity window and produces at least one `VERIFIED_PRE_MATCH`
  lineup with a real previous lineup to compare against.

## Acceptance checklist

- [x] Feature computed only from a `VERIFIED_PRE_MATCH` lineup — never from unknown/post-match
      provenance (§6).
- [x] Comparison baseline bounded by `information_available_at`, not wall-clock `now` — no
      future-fixture leakage into an earlier fixture's baseline (§6, test in §8).
- [x] No fabricated/hand-picked weight — a pure 0..1 ratio (§1).
- [x] Two independent home/away features, not an assumed-symmetric differential (§1).
- [x] `leakage_classification=PRE_MATCH_SAFE` set correctly, verified against `dev.db` (§5).
- [x] Wired only into the 14 confirmed genuinely-trained markets' `required_features`, verified
      against `dev.db` (§5); the 5 heuristic markets correctly untouched.
- [x] `required_features` change confirmed inert for already-serving Champions — traced through
      `PredictionEngine._resolve_predictor` before any code was written (§2).
- [x] Historical-data safety verified live: 0 lineups reclassified, 0 feature values backfilled
      retroactively (§7).
- [x] Design flaw (home/away ambiguity) caught and fixed before any test ran, not discovered by
      a failing assertion (§4).
- [x] 9 new unit tests + existing seeder tests updated; full backend suite green (§8, §9).
- [x] No training, retraining, or model promotion triggered by this milestone.
- [x] No new database schema/migration — reuses Milestone 5's existing fields.

## Stop condition

Per the standing process, this report is the stop point. **Do not automatically proceed to
Milestone 7** — the next candidate scope (wiring this feature into the 5 heuristic markets, or a
different Milestone 6 recommendation entirely) needs explicit user review and approval first.
