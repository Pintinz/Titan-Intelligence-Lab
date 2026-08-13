# Milestone 15 Pre-Implementation Audit — Historical Feature Backfill Into Training Data

Read-only audit, performed directly against the repository and (read-only) `dev.db`. No code was
modified, no writes occurred.

## 1. Existing Backfill Scripts

| Script | Sport | Market | Purpose | Reads `Prediction.feature_snapshot`? | Invokes `DatasetBuilder`? | Has fixture IDs? | Has kickoff (`scheduled_at`)? | Writes DB state? |
|---|---|---|---|---|---|---|---|---|
| `backfill_correct_score_training_data.py` | football | `football.correct_score` | Construct real `Prediction`/`PredictionOutcome` rows for a multiclass market that never had a Champion | No (constructs it) | No | Yes | Yes | Yes (`predictions`, `prediction_outcomes`) |
| `backfill_line_aware_markets_training_data.py` | football | 11 `NOT_YET_TRAINED_MARKET_KEYS` (Poisson-threshold markets) | Same unblock, applied to 11 binary markets at once | No (constructs it) | No | Yes | Yes | Yes |
| `backfill_match_winner_training_data.py` | football | `football.match_winner` | Retire a placeholder Champion + backfill real training rows | No (constructs it) | No | Yes | Yes | Yes |
| `backfill_both_teams_to_score_training_data.py` | football | `football.both_teams_to_score` | Retire a placeholder Champion + backfill real training rows | No (constructs it) | No | Yes | Yes | Yes |

None of the four invoke `DatasetBuilder` directly — all four construct `Prediction`/
`PredictionOutcome` rows one-off; `DatasetBuilder` runs later, unmodified, whenever
`ScheduledRetrainingOrchestrator`'s bootstrap loop next builds a `Dataset` from whatever
`PredictionOutcome` rows already exist. None of the four reconstruct historical news features
today — all four build `feature_snapshot` by reading whatever the offline Feature Store already
has for each fixture at backfill time, via each script's own small, hardcoded
`REQUIRED_FEATURES`/`OPTIONAL_FEATURES` tuple.

## 2. Candidate Comparison

| Candidate market | Real trained Champion path? | Working backfill script? | M9 `MARKET_IMPACT_RULES` entry? | Required-feature wiring in `market_seeding.py`? |
|---|---|---|---|---|
| `football.correct_score` | Yes | Yes | No (multiclass, no direct news rule) | No |
| 11 line-aware markets | Yes | Yes | No | No |
| `football.match_winner` | Yes | Yes | No (`MARKET_IMPACT_RULES` has no `football.match_winner` entry) | No |
| **`football.both_teams_to_score`** | **Yes** | **Yes** | **Yes — `btts_impact` dimension, forward/goalkeeper injury+suspension+recovery rules** | **Yes — `news.football.home_btts_impact`/`away_btts_impact` already in `required_features`** |

`football.both_teams_to_score` is the only candidate with all three: a real trained-Champion path,
a working backfill script, and a genuine, already-registered M9 market-specific news feature
mapping producing exactly the feature keys this integration would populate. Selecting it required
no invented feature-key wiring — the market's own `market_seeding.py` entry has named these two
keys as required since Milestone 9.

## 3. Selected Market

**`football.both_teams_to_score`.**

## 4. Selected Backfill Script

**`scripts/backfill_both_teams_to_score_training_data.py`.**

## 5. Existing Data Flow (traced)

```
main()
  -> resolve market by key, retire placeholder Champion if present (idempotent, no-op on re-run)
  -> register (or reuse) a non-Champion "backfill-anchor" ModelDefinition
  -> SELECT fixture IDs WHERE status='completed' AND home_score IS NOT NULL
  -> for each fixture:
       -> skip if a football.both_teams_to_score Prediction already exists for this fixture
          (idempotency guard #1, already exists)
       -> read home_score/away_score/scheduled_at
       -> read REQUIRED_FEATURES from feature_values_offline (skip fixture if any missing)
       -> read OPTIONAL_FEATURES from feature_values_offline (best-effort)
       -> resolve the real outcome via MARKET_OUTCOME_RESOLVERS
       -> record a Prediction (DRAFT status, inert placeholder value/probability/confidence)
       -> record a PredictionOutcome (real actual_value + error)
  -> commit
```

`DatasetBuilder` is never called here — it runs later, elsewhere, unmodified, reading whatever
`Prediction`/`PredictionOutcome` rows already exist by the time `ScheduledRetrainingOrchestrator`
next sweeps. This script's only job is to make those rows exist.

## 6. Integration Point

Confirmed: `HistoricalFeatureReconstructionService.publish_for_fixture(...)` must execute **inside
the per-fixture loop, immediately after the existing `list_by_subject` skip-check and the
`home_score/away_score/scheduled_at` read, and strictly before `REQUIRED_FEATURES`/
`OPTIONAL_FEATURES` are read from `feature_values_offline`** — exactly the required order (`fixture
→ reconstruct → read snapshot → [later, elsewhere] DatasetBuilder`), never the reverse.

This placement also gives idempotency "for free": a fixture that already has a
`football.both_teams_to_score` Prediction is skipped by the existing check *before* reconstruction
would ever run again for it — the same mechanism that already makes re-running this script safe
today. A secondary guard is still added (§8) for the case where a fixture is reconstructed but then
skipped for an unrelated reason (missing a different required feature) before a Prediction is ever
created, so reconstruction is never re-appended as a duplicate offline row on a later re-run.

Additionally required: reading `home_team_id`/`away_team_id` from `fixtures` (not currently
selected by this script) to build the `HistoricalFixtureContext`/`publish_for_fixture` call.

## 7. `DatasetBuilder` Analysis

Confirmed (re-verified against `modules/predictions/application/dataset_builder_service.py`):
`DatasetBuilder` sources every training sample exclusively from `Prediction.feature_snapshot`,
paired with its resolved `PredictionOutcome` — "no algorithm may bypass the Feature Store" is
enforced by construction, unchanged since Milestone 9.1. **`DatasetBuilder` requires zero
modifications.** This milestone's entire effect on it is indirect: if reconstruction produces an
eligible historical BTTS-impact value, the backfill script's own `feature_snapshot` dict (already
built from real Feature Store reads) will include it exactly like every other optional feature
already does — `DatasetBuilder` has no idea (and needs no idea) where any individual key in that
dict came from.

## 8. Provenance Analysis

`NewsMarketImpactEngine.compute_and_write`/`team_contributions` (Milestone 9/10/14, unmodified by
this integration) already gates every contribution on `NewsEvent.is_feature_eligible()`
(`VERIFIED_PRE_MATCH` + every entity resolved) and, when a `kickoff` is supplied,
`is_information_available_before_kickoff`. `HistoricalFeatureReconstructionService.publish_for_fixture`
(Milestone 14, unmodified) passes the fixture's own `scheduled_at` for all three of `now`/
`kickoff`/`historical_reference_time`. This script will call `publish_for_fixture` with the
fixture's real `scheduled_at` — no new provenance logic is written in the training script itself,
satisfying "training scripts do not implement provenance rules."

Since zero `VERIFIED_PRE_MATCH` news events exist anywhere in `dev.db` today (confirmed, again, in
this audit — see §10), a live run of the integrated script would call `publish_for_fixture` ~6,000+
times and receive `[]` (nothing written) every single time. This is the correct, expected, safe
behavior — not a defect to fix in this milestone.

## 9. Leakage Analysis

- **Wrong fixture**: `publish_for_fixture` is only ever called with the specific fixture's own
  `home_team_id`/`away_team_id`/`scheduled_at`, read fresh from that fixture's own row — no
  "current schedule" lookup exists anywhere in this integration.
- **Wrong market**: `NewsMarketImpactEngine` writes exactly the `btts_impact` dimension (and
  `goal_impact`/`clean_sheet_impact`, which this script simply never reads since they're not in
  its `OPTIONAL_FEATURES` list) — no cross-market leakage is possible since each dimension's
  feature key is distinct and the script only reads the two BTTS keys it adds.
- **Current-state leakage**: already closed at the source in Milestone 14 (`NewsMarketImpactEngine`'s
  historical roster path never reads `Player.team_id`/KG `PLAYS_FOR`) — this script does not
  reimplement or duplicate that logic, only calls into it.

## 10. Expected Database Writes

**None**, given `dev.db`'s current real state (zero `VERIFIED_PRE_MATCH` news events). All
verification in this milestone uses isolated, file-based `tmp_path` SQLite databases, never
`dev.db`. Read-only inspection of `dev.db` confirms:

```
predictions (market=football.both_teams_to_score): 729 rows, status='published'
fixtures (status='completed', home_score IS NOT NULL): 6444 rows
feature_definitions (news.football.{home,away}_btts_impact): 2 rows (already registered, from
  prior market seeding — confirms ensure_registered() has already run against this DB)
```

The large gap between 6444 completed fixtures and 729 existing predictions is explained by the
script's own `skipped_missing_required` counter (most fixtures lack one of the two hardcoded
`REQUIRED_FEATURES`), not by anything this milestone changes.

## 11. External API Assessment

None required. `publish_for_fixture` never contacts RSS/Gemini/any provider — it only reads
already-persisted `NewsEvent` rows via `events.list_for_entity`. Verification will use isolated
test databases with hand-constructed `Transfer`/`NewsEvent`/`Fixture` fixtures, never a real
provider call.

## 12. STOP-Condition Assessment

Checked against all 20 mandatory STOP conditions — none apply:

1. No schema migration needed (all required tables/columns already exist).
2. `DatasetBuilder` needs zero changes (§7).
3. No provenance gate is weakened — `is_feature_eligible()` is called exactly as before, via the
   unmodified `NewsMarketImpactEngine`.
4/5. `BACKFILL`/`ADMIN_MANUAL` cannot become `VERIFIED_PRE_MATCH` — unchanged Milestone 9 rule,
   this integration adds no new trigger value and doesn't touch `classify_news_availability`.
6/7. Post-kickoff/`UNKNOWN_AVAILABILITY_TIME` cannot enter — enforced by the unmodified engine.
8/9. `Player.team_id`/KG `PLAYS_FOR` are not required — the historical roster path already avoids
   both (Milestone 14).
10. Historical membership is never guessed — `HistoricallyUnresolved` cleanly excludes.
11/12. Wrong-market/wrong-fixture news is excluded by construction (§9).
13. Idempotency is achievable via the existing skip-check placement + one added guard (§6, §8).
14. No real RSS/Gemini call is needed for verification.
15. No `dev.db` write is required or will occur during this milestone's implementation/verification.
16. No model training is needed — this script never called `.fit()` before and doesn't after.
17. No Champion/model-registry change beyond what the script *already* does (retiring a
    placeholder Champion) — unchanged by this milestone.
18. `DatasetBuilder` semantics are not touched.
19. No new provider is required.
20. Community Intelligence is not touched.

**No STOP condition applies. Proceeding to Phase 2 implementation.**

## 13. Implementation Plan

1. Add `home_team_id`/`away_team_id` to the fixture row query.
2. Compose `HistoricalFeatureReconstructionService` once at the top of `main()` via
   `apps.api.composition.build_historical_feature_reconstruction_service`, and call
   `ensure_registered(now)` once (idempotent, matching the existing `FootballMarketSeeder` pattern).
3. Inside the per-fixture loop, immediately after the existing `list_by_subject` skip-check: if
   neither `news.football.home_btts_impact` nor `news.football.away_btts_impact` already has a
   value for this fixture (idempotency guard), call
   `service.publish_for_fixture(fixture_id, home_team_id, away_team_id, scheduled_at)`.
4. Add `"news.football.home_btts_impact"` and `"news.football.away_btts_impact"` to
   `OPTIONAL_FEATURES` (never `REQUIRED_FEATURES` — making them required would break every
   existing fixture today, since zero eligible historical news exists yet; optional matches this
   script's own established pattern for the 5 stat-differential features).
5. No change to `DatasetBuilder`, `NewsMarketImpactEngine`, `HistoricalFeatureReconstructionService`,
   or `HistoricalNewsRelevanceEngine` — reuse only.
6. Write the full test matrix (15 items) against isolated `tmp_path` SQLite databases.
7. Run targeted + full regression suite, compare against the Milestone 14 baseline (2180/58/0).
8. Write `docs/milestone15_verification_report.md`, confirm `dev.db` untouched, STOP.
