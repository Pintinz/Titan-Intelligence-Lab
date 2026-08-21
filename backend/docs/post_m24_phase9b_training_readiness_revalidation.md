# POST-M24 Master Data Fabric — Phase 9B Verification Report

## Final Training Readiness Revalidation (Post Team-Statistics Enrichment)

**Date:** 2026-08-16
**Scope:** Re-verify team_statistics enrichment directly against `dev.db` → trace exactly how (or
whether) those statistics reach any training-relevant feature → re-run the official preflight
unmodified → prove BEFORE/AFTER equivalence with a real diff, not an assumption. No training, no
Champion changes, no calibration, no Celery Beat.

---

## 1. Executive Summary

The team-statistics enrichment work (Phase 9's follow-on session) is real and independently
re-verified against `dev.db`: 552/552 English League Two fixtures, 11/63 DFB-Pokal fixtures, and
46/760 Premier League fixtures now carry genuine `team_statistics` rows (shots, shots-on-target,
corners, fouls, cards, and — for the two API-Football-sourced competitions — possession).

Tracing how this data is actually consumed (Part 4) confirms it only ever reaches training through
`FixtureFormDifferentialCalculator`, which reads `TeamStatisticsRepositoryPort.list_recent_by_team`
under a strict `Match.started_at < before` filter — a legitimate historical-rolling pattern, never
the current match's own post-match stats leaking into that same match's prediction. This part of
the architecture is leakage-safe by construction and required no fix.

**Re-running the official, unmodified preflight (`scripts/run_training_preflight.py
--all-trained-football`) produces byte-for-byte identical output to the pre-enrichment baseline** —
confirmed with a real `diff`, not an assumption. **0/14 markets are ready.** The reason is
structural, not a data-volume problem: the new statistics landed on English League Two and
DFB-Pokal fixtures, both of which have **zero** `prediction_outcomes` (never bootstrapped/labeled),
so they never enter `DatasetBuilder`'s training sample set at all — only the pre-existing 823-828
Premier League samples do, and those gained at most one additional fixture's worth of rolling-window
signal (Premier League coverage moved from 45→46), not enough to shift any aggregate coverage
percentage past the 50% threshold. The two universal blockers from Phase 9 — `lineup_continuity`/
`transfer_activity` at 0% real coverage, and no `Dataset` ever durably persisted — are completely
unrelated to team statistics and remain exactly as they were.

**No code was changed this phase.** No market reached READY. Champion set, predictions, datasets,
and calibration reports are all byte-for-byte unchanged from both the Phase 9 baseline and this
phase's own opening snapshot.

---

## 2. Runtime Status (Part 1)

| Component | Status |
|---|---|
| Frontend | UP — port 5173 listening |
| Backend | UP — port 8000 listening, `--reload` active (unchanged from the prior session, no restart needed) |
| Redis | UP — port 6379 listening |
| Backend → Database | Confirmed — `/docs` returns 200, a protected fixtures endpoint returns 401 without auth (correct behavior, not an error) |

Celery Beat: **not started**.

---

## 3. Database Baseline (Part 2)

Read-only snapshot at the start of this phase:

| Table | Count |
|---|---|
| fixtures | 7,386 |
| matches | 742 |
| teams | 236 |
| competitions | 8 |
| seasons | 22 |
| feature_definitions | 47 |
| feature_values_offline | 72,744 |
| feature_values_online | *(no DB table — Redis-only, unchanged from Phase 9)* |
| prediction_markets | 43 |
| prediction_outcomes | 11,194 |
| predictions | 12,436 |
| datasets | 0 |
| models | 47 (19 champion / 14 candidate / 14 retired) |
| calibration_reports | 0 |
| players | 100 |
| player_statistics | 0 |
| market_lines | 0 |
| news_articles | 319 |
| news_events | 68 |
| provider_ref_index | 8,110 |
| sync_runs | 507 |
| sync_checkpoints | 305 |
| team_statistics | 1,478 |

`champion_set_hash` (SHA-256 over every champion row's `id|market_id|model_key|version|algorithm|
artifact_ref|dataset_version|promoted_at`, ordered by `model_key`):
`cc5deabbfdb7d9e709d70bbaf885c199dd66306ca35b46f0ec5d028310541312` — **identical to Phase 9's own
recorded hash**, confirming zero Champion drift across the entire team-statistics enrichment work.

`matches` (742) and `sync_runs` (507) are higher than Phase 9's snapshot (178 / 405) purely because
of the team-statistics backfill's own real writes: +564 matches (552 League Two + 10 DFB-Pokal +
2 from the very first live test — every `get_or_create_match` call for a fixture that received real
stats) and +102 sync_runs (from the live `sync_team_statistics_for_fixture` batch, which — unlike
the League Two CSV backfill's direct reconciler calls — goes through `SyncOrchestrator._run_sync`
and records one `SyncRun` per attempt). Both deltas are arithmetically exact and expected, not
anomalies.

---

## 4. Team Statistics Verification (Part 3) — Independently Re-Queried, Not Assumed

Direct query against `dev.db`, joining `fixtures → seasons → competitions → matches →
team_statistics`:

| Competition | Completed fixtures | With `team_statistics` |
|---|---|---|
| English Football League Two | 552 | **552** |
| DFB-Pokal | 63 | **11** |
| Premier League | 760 | **46** |
| EuroLeague | 331 | 20 |
| MLB | 2,931 | 40 |
| NBA | 1,377 | 40 |
| NPB | 982 | 30 |

Every number matches the prior session's claim exactly — independently re-derived, not trusted from
the report.

**Safety checks, all confirmed real:**
- **Non-completed fixtures with `team_statistics`: 0.** No scheduled/live/postponed/cancelled
  fixture carries any statistics — nothing was fabricated ahead of a real result.
- **Provenance is correct and source-specific**: League Two rows carry
  `{"historical:web:football_data_co_uk:E3:2324": "web:football_data_co_uk:E3:2324:<row>"}`;
  DFB-Pokal/Premier League rows carry `{"api_football": "<real fixture id>"}`. Never mixed, never
  defaulted.
- **Not score-derived**: sampled rows show real, independently-varying values (e.g. two 3-0 League
  Two results with completely different shot/corner/card counts) — no formula ties `stat_set` to
  `final_state`.
- **Not copied between fixtures**: every `team_statistics` row's `match_id`/`team_id` pair is
  unique per fixture side; no duplicate `stat_set` blocks were observed across different matches
  during this or the original backfill's own verification.

---

## 5. Feature Consumption Audit (Part 4) — The Critical Trace

Directly read `modules/predictions/application/windowed_feature_engineering_service.py`:

```
raw team_statistics
      ↓ (TeamStatisticsRepositoryPort.list_recent_by_team, team_id, before=now, limit=5)
FixtureFormDifferentialCalculator._team_average()
      ↓ (home_average - away_average)
FeatureStoreService.write(feature_key, EntityType.FIXTURE, fixture_id, value, now)
      ↓
feature_values_offline (for training) / online Redis store (for inference — same write path)
```

**This is a single calculator, one code path, for both training and inference** — there is no
separate "online" vs. "offline" implementation to drift apart; `compute_and_write` is called by the
same `windowed_feature_engineering_service` regardless of whether the caller is backfilling
historical fixtures or reconciling a just-completed live one. Training/inference parity for this
specific feature family is structurally guaranteed by construction, not something that needed
re-auditing feature-by-feature.

**Six real features exist in this family**, all registered under `EntityType.FIXTURE`:

| Feature key | `stat_key` read from `team_statistics.stat_set` | Window |
|---|---|---|
| `football.fixture.form_possession_pct_diff_last5` | `possession_pct` | last 5 |
| `football.fixture.form_shots_total_diff_last5` | `shots_total` | last 5 |
| `football.fixture.form_shots_on_target_diff_last5` | `shots_on_target` | last 5 |
| `football.fixture.form_corners_diff_last5` | `corners` | last 5 |
| `football.fixture.form_fouls_diff_last5` | `fouls` | last 5 |
| `football.fixture.form_cards_yellow_diff_last5` | `cards_yellow` | last 5 |

**Which markets require them, and how**: `market_seeding.py`'s `_seed_market` computes
`is_required = feature_key not in _NEW_STAT_DIFFERENTIAL_FEATURES and feature_key not in
market_optional_features`. `_NEW_STAT_DIFFERENTIAL_FEATURES` contains 5 of the 6 (everything except
`form_shots_on_target_diff_last5`) — those 5 are **globally optional** for every market that maps
them; `DatasetBuilder`/the preflight never gate on them. `form_shots_on_target_diff_last5` is the
one exception: it is mapped as a **required** feature on several markets, including
`football.correct_score`, `football.both_teams_to_score`, and `football.match_winner` (confirmed
directly from the live `feature_market_mappings` table, not just the current `market_seeding.py`
source — the two can differ, since the seeder is insert-only and never retracts an older mapping;
the preflight always reads the real table, which is what governs actual readiness).

**Leakage safety (Part 9/10)**: `list_recent_by_team` filters `Match.started_at < before` — every
value that ever reaches `_team_average` is drawn from matches that had already **finished** before
the fixture being predicted **kicked off**. This is exactly the acceptable pattern Phase 9B's own
instructions describe (Match N's prediction uses Matches N-1..N-5's statistics) — never Match N's
own final statistics. No leakage exists in this feature family, and none was introduced by the
enrichment (the enrichment added more real historical rows to draw from; it changed no query logic).

**Which markets "benefit"**: in principle, any of the 14 candidate markets whose required features
include `form_shots_on_target_diff_last5`, and any market (required or optional) reading the other
5 stat-diff features, benefit from *more real historical coverage* the next time a model is
actually trained. In practice, for *this specific* enrichment: League Two and DFB-Pokal fixtures
only affect the rolling windows of the specific clubs that played in them — English League Two and
German cup clubs, not Premier League teams — so they have **zero** effect on the already-labeled
Premier League training samples the 14 candidate markets actually use. Only the +1 real Premier
League fixture (45→46) could theoretically touch a Premier League team's own rolling window, and
one additional data point does not meaningfully move an aggregate coverage percentage computed over
653-828 samples.

---

## 6. Preflight — Before vs. After (Part 5/6) — Proven With a Real Diff

Ran the repository's own unmodified tool: `scripts/run_training_preflight.py
--all-trained-football`, identical invocation to Phase 9.

**Result: `diff phase9_preflight_before.log phase9b_preflight_after.log` — zero lines of output.**
The two runs are byte-for-byte identical, including every check's exact detail string (e.g.
`football.fixture.form_shots_on_target_diff_last5=1.9%` appears unchanged in both).

**0/14 markets READY, same as Phase 9, for the same two universal reasons**:

| Market | training_inference_feature_parity | required_feature_coverage_acceptable | dataset_provenance_persisted |
|---|---|---|---|
| All 14 (correct_score, total_goals_over_under ×6, home/away_win_to_nil, home/away_team_total_goals, home/away_clean_sheet, match_winner, both_teams_to_score) | FAIL — `lineup_continuity`/`transfer_activity` (4 keys) absent from every sample, unchanged | FAIL — same 4 keys at 0.0%, plus market-specific extras (e.g. correct_score's `form_shots_on_target_diff_last5`=1.9%, unchanged) | FAIL — 0 Dataset rows for any market, unchanged |

Every other check (`market_exists`, `feature_manifest_declared`, `sufficient_labeled_observations`,
`labels_valid`, `temporal_reference_present`, `temporal_split_valid`, `feature_versions_known`,
`intelligence_feature_leakage_safe`, `dataset_reproducible`) **continues to pass** for all 14
markets, exactly as in Phase 9.

**No newly satisfied gates. No newly failing gates. No unchanged-but-different values. Zero
observable effect from the team-statistics enrichment on training readiness.**

---

## 7. Training/Inference Parity (Part 7)

Already covered in §5: the stat-differential feature family shares one calculator for both training
(historical backfill/reconciliation) and inference (live reconciliation) — there is structurally no
opportunity for the two paths to diverge, since it is the same code object (`compute_and_write`)
invoked either way. No separate audit of key/scope/datatype/transformation compatibility was
needed because there is no second implementation to compare against.

The `lineup_continuity`/`transfer_activity` parity failure (the actual blocker) is unrelated to team
statistics and was already fully traced in Phase 9 §5 — re-confirmed unchanged here (§6 above).

---

## 8. Dataset Provenance (Part 8)

Unchanged from Phase 9's own finding: `datasets` table remains at 0 rows for every market. The only
code path that ever calls `DatasetRegistryService.register()` is
`ScheduledRetrainingOrchestrator._build_validate_approve_dataset()`, invoked exclusively as step one
of an actual retraining attempt — which has never run. This is the correct, expected state, not a
defect, and nothing about the team-statistics enrichment touches this path at all (the enrichment
only writes `team_statistics` rows via `EntityReconciliationService.reconcile_team_statistics`,
never anything in `modules/predictions/`).

Historical rows remain correctly tagged `BACKFILL` (League Two) or their real live-sync trigger
(DFB-Pokal/Premier League `team_statistics`, which — unlike fixtures — carries no `SyncTrigger`
field at all; provenance for this entity type lives entirely in `provider_ref`, verified correct
in §4). No relabeling to `VERIFIED_PRE_MATCH` occurred or was attempted.

---

## 9. Leakage Audit (Part 9/10)

Covered in full in §5. Summary: the only new training-relevant signal from this enrichment
(`form_shots_on_target_diff_last5` coverage, marginally, for Premier League) is consumed through a
strict pre-kickoff rolling window (`Match.started_at < before`). No post-match statistic from a
fixture being predicted is ever fed into that same fixture's own prediction. Leakage-safe.

---

## 10. Historical Odds Assessment (Part 11)

Unchanged from Phase 9 §7: only `football.match_winner` among the 14 candidates requires
odds-derived features (`football.market.implied_probability_home`/`away`), and those already clear
`required_feature_coverage_acceptable` on their own (not part of the failing-checks list). Odds
were not touched this phase; no new odds work was needed or attempted.

---

## 11. Market-by-Market Readiness / Data Sufficiency (Part 12/13)

Identical to Phase 9 §4/§9 — re-confirmed via the identical preflight output. All 14 candidates
retain their real, well-above-minimum sample counts (653-828), and no other market (basketball,
baseball, table tennis, the 4 non-trained football markets) gained any `prediction_outcomes` this
phase — still 0 for all of them, confirmed by the same direct query pattern Phase 9 used.

---

## 12. Code Changes (Part 14)

**None.** No defect was found that this phase's own rules would permit fixing. Both blockers
(feature parity + data deficit on `lineup_continuity`/`transfer_activity`; dataset provenance
correctly reflecting "no training has ever run") are legitimate, already fully traced in Phase 9,
and re-confirmed unchanged here by direct evidence rather than re-asserted from memory.

## 13. Database Migration (Part 15)

Not applicable — no schema change was found to be required.

---

## 14. Tests (Part 16)

No code was changed this phase, so no new tests were written. The most recent real full backend
suite run in this session (immediately prior to this phase, after the completed-matches stats-strip
work) was **2,423 passed / 58 skipped / 0 failed** — since nothing in the repository changed between
that run and this phase's conclusion, that result remains the accurate, current state and was not
re-run redundantly.

---

## 15. Database Delta

**Zero** for this phase specifically — every table count recorded in §3 is identical at the end of
this phase (confirmed by re-querying `champion_set_hash`, `predictions`, `prediction_outcomes`,
`datasets`, `calibration_reports`, `models` immediately before writing this report). All database
changes described in this report (the 552+11+1 `team_statistics` rows, +564 `matches`, +102
`sync_runs`) were made in the *prior* session turn, before Phase 9B began — this phase itself
performed zero writes (read-only investigation and an unmodified preflight re-run only).

---

## 16. Champion Safety (Part 18)

| Check | Result |
|---|---|
| Champion count | 19 → 19, unchanged |
| `champion_set_hash` | Identical: `cc5deabb...` |
| predictions | 12,436 → 12,436, unchanged |
| prediction_outcomes | 11,194 → 11,194, unchanged |
| datasets | 0 → 0, unchanged |
| calibration_reports | 0 → 0, unchanged |

No unexpected mutation. No investigation triggered.

---

## 17. Final Decision

**NO MARKET IS LEGITIMATELY READY FOR TRAINING.**

## 18. First Recommended Market

None currently ready. If forced to name the single closest candidate for a *future* phase once the
lineup/transfer-continuity data deficit resolves (via real, live-scheduled sync over time — not
fabrication), `football.match_winner` remains the best-positioned: it already clears every check
except the two universal blockers, has the richest real feature set (12 mapped features, including
the now better-covered stat-differentials), and needs no odds work.

## 19. Exact Remaining Blockers

1. **`lineup_continuity`/`transfer_activity` — 0% real coverage, universal across all 14 candidate
   markets.** Root cause unchanged from Phase 9: zero `VERIFIED_PRE_MATCH` lineup/transfer records
   exist anywhere in `dev.db` (4 lineups, 308 transfers, all `UNKNOWN_AVAILABILITY_TIME`). The only
   path to that classification is a live, near-kickoff `LIVE_SCHEDULED` sync running on a real
   schedule, which requires Celery Beat — explicitly out of scope/prohibited every phase so far.
   Team-statistics enrichment cannot and did not affect this; it is an entirely separate feature
   family.
2. **No durable `Dataset` has ever been persisted for any market.** Correct, expected state given
   no training run has ever legitimately executed — resolves automatically as step one of a real,
   authorized training run, not before.
3. Basketball/baseball/table_tennis and the 4 non-trained football markets still have zero labeled
   `prediction_outcomes` — unrelated to this phase's enrichment, unchanged from every prior phase.
