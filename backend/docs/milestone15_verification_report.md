# Milestone 15 Verification Report — Historical Feature Backfill Into Training Data

## 1. Executive Summary

Milestone 15 connects Milestone 14's `HistoricalFeatureReconstructionService` — built but, by its
own docstring, "not wired into any live endpoint, Celery task, or training script" — to one real
training-data backfill script, so historical news-derived features can (once real
`VERIFIED_PRE_MATCH` events exist) actually enter the training data `DatasetBuilder` reads, rather
than remaining permanently inert. The integration is minimal by design: no new provenance,
entity-resolution, or leakage logic was written; the script only calls existing Milestone 13/14
services and reads whatever they publish, exactly like every other optional feature it already
reads. `DatasetBuilder` required zero changes. All 20 mandatory STOP conditions were checked in
the pre-implementation audit (`docs/milestone15_preimplementation_audit.md`) and none applied.

## 2. Initial Audit Findings

Phase 1's mandatory read-only audit (`docs/milestone15_preimplementation_audit.md`) compared all
four existing `scripts/backfill_*_training_data.py` scripts against the full set of markets with a
real Milestone 9 `MARKET_IMPACT_RULES` entry, a working backfill script, and existing
required-feature wiring in `market_seeding.py`. Only `football.both_teams_to_score` satisfied all
three — the `news.football.home_btts_impact`/`away_btts_impact` keys have been named in that
market's `required_features` since Milestone 9, so no new feature-key wiring was invented for this
milestone. `DatasetBuilder` was re-confirmed to source every training sample exclusively from
`Prediction.feature_snapshot` — "no algorithm may bypass the Feature Store" holds by construction,
unchanged since Milestone 9.1. The offline Feature Store write path
(`SqlAlchemyFeatureValueRepository.record`) was found to be a plain INSERT, not an upsert — driving
this milestone's idempotency-guard design (§11).

## 3. Files Created

- `docs/milestone15_preimplementation_audit.md` — Phase 1 audit (13 sections).
- `tests/unit/scripts/__init__.py` — new test package (no backfill script had a test file before).
- `tests/unit/scripts/test_backfill_both_teams_to_score_training_data.py` — 15-item test matrix.
- `docs/milestone15_verification_report.md` — this report.

## 4. Files Modified

- `scripts/backfill_both_teams_to_score_training_data.py` — the sole implementation change (§5-§7).
- `apps/api/composition.py` — `build_historical_feature_reconstruction_service`'s docstring updated
  from "not yet wired into any live endpoint, Celery task, or training script" to reflect that this
  milestone wired it into this one training script (a comment-only change; the factory itself,
  along with everything it composes, is untouched).

## 5. Script Integration Point

`HistoricalFeatureReconstructionService.publish_for_fixture(...)` is called once per fixture,
inside the existing per-fixture loop, immediately after the pre-existing `list_by_subject`
skip-check and the `home_score`/`away_score`/`scheduled_at` read, and strictly before
`REQUIRED_FEATURES`/`OPTIONAL_FEATURES` are read from `feature_values_offline` — the required
order (`fixture → reconstruct → read snapshot → [later, elsewhere] DatasetBuilder`), never the
reverse. `home_team_id`/`away_team_id` were added to the fixture row's `SELECT` (not previously
selected by this script) to build the call. The service is composed once, at the top of `main()`,
via `apps.api.composition.build_historical_feature_reconstruction_service`; `ensure_registered` is
called once immediately after (idempotent, matching the existing `FootballMarketSeeder` pattern).

## 6. Historical Reference Time

`publish_for_fixture` is called with the fixture's own `scheduled_at` (computed once as `kickoff`,
falling back to `now` only if `scheduled_at` is unexpectedly null) for the single
`historical_reference_time` parameter, which Milestone 14 threads through as `now`, `kickoff`, and
`historical_reference_time` simultaneously to `NewsMarketImpactEngine.compute_and_write`. This
script never substitutes real wall-clock "today" for any of these — doing so would make every
historical event's age/TTL check evaluate against the wrong clock and incorrectly treat every
historical event as expired.

## 7. Feature Reading

Two new optional feature keys were added to `OPTIONAL_FEATURES` (never `REQUIRED_FEATURES` —
required would skip every fixture today, since zero eligible historical news exists anywhere yet):
`news.football.home_btts_impact` and `news.football.away_btts_impact`, exposed as the
`NEWS_BTTS_IMPACT_FEATURES` constant. They are read through the script's own pre-existing
`_latest_feature_value` helper, identically to the five stat-differential optional features already
read the same way — no new read path was written.

## 8. `DatasetBuilder` Impact

None, confirmed by both the Phase 1 audit and this milestone's own re-reading of
`dataset_builder_service.py`: it is untouched, and needs no awareness of where any individual
`feature_snapshot` key came from. This milestone's entire effect on training data is indirect — if
reconstruction produces an eligible historical BTTS-impact value, the backfill script's own
`feature_snapshot` dict (already built from real Feature Store reads) includes it exactly like
every other optional feature it already includes.

## 9. Provenance Enforcement

Unchanged from Milestones 9/13/14, reused without modification: `NewsEvent.is_feature_eligible()`
(`VERIFIED_PRE_MATCH` + every entity resolved) and, since a `kickoff` is always supplied,
`is_information_available_before_kickoff`. `BACKFILL`/`ADMIN_MANUAL` sync triggers cannot produce
`VERIFIED_PRE_MATCH` (`classify_news_availability`, Milestone 9/10) — re-confirmed directly in
tests 05/06 of this milestone's own test matrix, not assumed.

## 10. Entity Resolution Integration

Reused without modification: `HistoricalEntityResolutionService` (Milestone 13) resolves roster
membership via the `Transfer` chain only; `NewsMarketImpactEngine._resolve_roster` (Milestone 14)
never calls `Player.team_id` or Knowledge Graph `PLAYS_FOR` edges when a `historical_reference_time`
is supplied. Re-confirmed for this specific integration in tests 07/08 (a later transfer does not
retroactively change kickoff-time membership; a deliberately stale/conflicting `Player.team_id`
field is never consulted).

## 11. Idempotency

Two independent guards, both required:

1. **Existing (unchanged):** the script's own `list_by_subject` skip-check — a fixture that already
   has a `football.both_teams_to_score` `Prediction` is skipped before reconstruction would ever be
   reached again, since reconstruction runs strictly after that check in the loop.
2. **New:** before calling `publish_for_fixture`, the script checks whether either BTTS-impact
   feature key already has a value for the fixture (via `_latest_feature_value`, the same helper
   used to read `REQUIRED_FEATURES`) and skips reconstruction if so. This guard exists because the
   offline Feature Store write path is append-only, not an upsert (§2) — it covers the case where a
   fixture was reconstructed on a prior run but never reached a `Prediction` (e.g. a different,
   unrelated required feature was missing that run), which the `list_by_subject` guard alone cannot
   catch. Verified directly by test 14: two full script runs against a fixture that is missing
   `football.market.overround` (so no `Prediction` is ever created) produce exactly one offline row
   for `news.football.home_btts_impact`, not two.

## 12. Leakage Analysis

- **Wrong fixture:** `publish_for_fixture` is only ever called with the specific fixture's own
  `home_team_id`/`away_team_id`/`scheduled_at`, read fresh from that fixture's own row.
- **Wrong market:** `NewsMarketImpactEngine` writes the `btts_impact` dimension distinctly from
  `goal_impact`/`clean_sheet_impact` — the script's `OPTIONAL_FEATURES` reads only the two BTTS
  keys, so a `goal_impact` value can never masquerade as a BTTS signal.
- **Current-state leakage:** closed at the source in Milestone 14, re-confirmed for this
  integration by test 08 above.
- **Unrelated-team leakage:** re-confirmed by test 09 — news attached to a team not playing in the
  fixture produces no written value.

## 13. Test Matrix (15 items)

All in `tests/unit/scripts/test_backfill_both_teams_to_score_training_data.py`, split into Part A
(service-level, reusing Milestone 14's established in-memory fixtures — no new provenance logic is
being tested here, only this market's own wiring of it) and Part B (script-level, against an
isolated file-based SQLite database built from the real production schema, never `dev.db`):

| # | Test | Result |
|---|---|---|
| 1 | Eligible pre-kickoff forward injury (home) produces `home_btts_impact` only | PASS |
| 2 | Eligible pre-kickoff forward injury (away) produces `away_btts_impact` only | PASS |
| 3 | Post-kickoff event excluded | PASS |
| 4 | `UNKNOWN_AVAILABILITY_TIME` event excluded | PASS |
| 5 | `BACKFILL` trigger never classifies `VERIFIED_PRE_MATCH` | PASS |
| 6 | `ADMIN_MANUAL` trigger never classifies `VERIFIED_PRE_MATCH` | PASS |
| 7 | Later transfer does not retroactively change kickoff-time membership | PASS |
| 8 | Stale/conflicting current `Player.team_id` field is never consulted | PASS |
| 9 | Unrelated-team news does not leak into the fixture | PASS |
| 10 | Unresolved membership (no transfer history) excludes the player | PASS |
| 11 | Script wires the two news keys as optional, never required | PASS |
| 12 | Reconstructed features land in `Prediction.feature_snapshot` (the exact path `DatasetBuilder` reads); side isolation holds end-to-end | PASS |
| 13 | Idempotent across two full script runs when a `Prediction` already exists (no duplicate `Prediction` or offline feature rows) | PASS |
| 14 | Idempotent when a fixture was reconstructed but never reached a `Prediction` (standalone guard, §11) | PASS |
| 15 | Regression: a fixture with zero eligible news behaves identically to the script's pre-Milestone-15 form (required features populate, no news keys appear) | PASS |

15/15 passed.

## 14. Regression Results

Full suite: **2195 passed, 58 skipped, 0 failed** (1180.73s), against the Milestone 14 baseline of
2180 passed/58 skipped/0 failed — a net +15, exactly the 15 new tests in this milestone's own
matrix, with zero pre-existing test broken or altered.

## 15. Database/Migration Status

No schema migration was needed or written — every table/column this milestone reads or writes
already existed (confirmed in the Phase 1 audit, §12 item 1). No Alembic revision was added.

## 16. `dev.db` Status

**Untouched.** Every test in this milestone's matrix runs against an isolated, file-based SQLite
database created fresh per test (`tmp_path`) with `TITANIQ_DB_URL` overridden via `monkeypatch` and
composition's `@lru_cache`d engine/settings explicitly cleared before and after — never the real
`dev.db`. The actual backfill script was not executed against `dev.db` during this milestone's
implementation or verification; `dev.db`'s on-disk modification time predates this milestone's
work. Because zero `VERIFIED_PRE_MATCH` news events exist anywhere in `dev.db` today (confirmed in
the Phase 1 audit), a real run of the integrated script against `dev.db` would call
`publish_for_fixture` for each of the ~6,000+ eligible fixtures and receive `[]` (nothing written)
every time — the correct, expected, safe behavior, not something this milestone needed to change or
verify further. Running the script for real against `dev.db` was intentionally not performed as
part of this milestone, consistent with "no `dev.db` write is required" from the Phase 1
STOP-condition assessment.

## 17. External API Status

None contacted, and none required. `publish_for_fixture` never calls RSS/Gemini/any provider — it
only reads already-persisted `NewsEvent` rows via `events.list_for_entity`. All verification used
hand-constructed `Transfer`/`NewsEvent`/`Fixture` fixtures in isolated test databases.

## 18. Training/Model Status

No model training occurred and none was triggered. This milestone never calls `.fit()`, never
touches `ModelRegistryService` beyond what the script already did before this milestone (retiring a
placeholder Champion and registering/reusing a non-Champion "backfill-anchor" model definition —
unchanged), and does not invoke `ScheduledRetrainingOrchestrator` or any Celery task.

## 19. Production Impact

None today. Since `dev.db` has zero `VERIFIED_PRE_MATCH` news events, running the integrated script
against production data would behave byte-for-byte identically to the pre-Milestone-15 script for
every existing fixture (confirmed by test 15's regression scenario) — the two new optional feature
keys simply never populate until a real, live-scheduled news sync (a separate, still-`false`-gated
capability — Milestone 10/12) produces at least one eligible event. This milestone's value is
purely infrastructural: the wiring now exists and is tested, so the moment real eligible historical
news exists, this script will pick it up with no further code change.

## 20. Known Limitations

- Only `football.both_teams_to_score` is wired — the other three backfill scripts
  (`correct_score`, the 11 line-aware markets, `match_winner`) do not have a corresponding
  `MARKET_IMPACT_RULES` entry today (confirmed in the Phase 1 audit's candidate comparison), so
  extending this pattern to them is blocked on Milestone 9-style market-impact-rule authoring, not
  on anything this milestone controls.
  Extending is additive — no existing wiring changes shape.
- The idempotency guard (§11) reads `_latest_feature_value` twice per fixture in the worst case
  (once for the guard, once, only if the guard passes and a `Prediction` is later created, no
  further reads) — negligible in absolute cost given this script's existing per-fixture
  `REQUIRED_FEATURES`/`OPTIONAL_FEATURES` read pattern already does the same kind of per-key query.
- As before Milestone 15, and unaffected by it: zero real historical news exists in `dev.db`, so
  this integration has no observable effect until that changes.

## 21. Deferred Work

- Wiring the same pattern into the other three backfill scripts, once their markets have a real
  `MARKET_IMPACT_RULES` entry.
- Any live/scheduled path that would actually populate `VERIFIED_PRE_MATCH` historical news remains
  out of scope — that is Milestone 10/12's `NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` territory,
  both still default-`false`, untouched by this milestone.
- Community Intelligence remains explicitly deferred, per the master command's own instruction.

## 22. Architectural Principles Honored

No new provenance logic, entity-resolution logic, or leakage rule was written in the training
script itself — every guarantee this milestone depends on was authored in Milestones 9/10/13/14 and
is reused, not reimplemented, in `scripts/backfill_both_teams_to_score_training_data.py`.
`DatasetBuilder` remains the sole and unmodified consumer of `Prediction.feature_snapshot`.
`HISTORICALLY_RELEVANT` never implies `FEATURE_ELIGIBLE` (Milestone 13/14's distinction is
untouched). No unvalidated model promotion, no training during inference, no data dumping —
this milestone touches exactly one script's feature-snapshot construction and nothing else.

## 23. Recommended Milestone 16 Scope

Not proposed here per the master command's instruction to await explicit Milestone 16
specification. If asked for a recommendation: author a `MARKET_IMPACT_RULES` entry (and
corresponding backfill-script wiring) for one of the three currently-unwired markets — most likely
`football.match_winner`, the highest-volume market among the remaining three — following this
milestone's exact pattern.

---

**dev.db confirmed untouched. No model training occurred. No live RSS/Gemini calls were made.**

MILESTONE 15 COMPLETE — WAITING FOR EXPLICIT APPROVAL FOR MILESTONE 16.
