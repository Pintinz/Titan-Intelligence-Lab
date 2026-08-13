# Milestone 20 — Final Production Challenger Training, Evaluation & Promotion

## Phase 0: Read-Only Discovery and Preimplementation Audit

Status: **PHASE 0 COMPLETE — STOPPING FOR EXPLICIT APPROVAL BEFORE ANY IMPLEMENTATION**

No file was modified to produce this document. No migration was applied. No model was trained.
`dev.db` was read-only for the entire audit — every check below ran through the read-only
`TrainingPreflightService` (built and verified in Milestone 19) or a direct
`sqlite3.connect("file:dev.db?mode=ro", uri=True)` query.

---

## 1. Executive Summary

Milestone 19's finding — 0 of 14 genuinely-trained football markets are training-ready — is
**reconfirmed, live, unchanged**, in this audit. `dev.db` row counts are byte-identical to the
Milestone 19 snapshot (verified below). Re-running `TrainingPreflightService` against all 14
markets today reproduces the identical failing checks, market for market, feature for feature.

This audit goes one step further than Milestone 19 by sweeping **every one of the 38 markets in
the catalog**, not just the 14 already known to be genuinely trained, and by tracing the *root
cause* of the parity failure to its logical conclusion: **the blocker is not a code defect and
cannot be fixed by any code change available to this session.** It is a structural property of
the platform's history — the historical fixtures that produced the 14 markets' training data
were never covered by a live `LIVE_SCHEDULED` sync, so no legitimate `VERIFIED_PRE_MATCH`
lineup/transfer/news observation was ever recorded for them, and none ever can be, because that
information would have to have been captured *before* those already-completed matches kicked
off — a window that has permanently closed. Fabricating it is explicitly forbidden (Milestone 20
§1, §6, §7), and this audit does not attempt to work around that prohibition.

**Bottom line: this audit's own findings point toward STATE C (TRAINING BLOCKED) as the honest
outcome for every market that currently has any training data at all.** Section 8 below identifies
the one, and only one, legitimately fixable gap (durable `Dataset` persistence) — fixing it would
not change the READY=0 result for any current market, since the parity/coverage checks fail
independently of it. This document stops here, per the master prompt's Phase 0 protocol, for
explicit direction on whether to (a) proceed straight to the Milestone 20 blocked-training report,
optionally including the one legitimately fixable persistence gap, or (b) something else.

---

## 2. M19 Baseline — Live Reconfirmation

| Check | Milestone 19 | Re-verified now |
|---|---|---|
| `dev.db` row counts (20 tables) | snapshot in M19 report §17/§20 | **identical**, re-queried this audit |
| `TrainingPreflightService` result, 14 trained football markets | 0/14 READY | **0/14 READY**, identical failing checks per market |
| Full test suite | 2222 passed / 58 skipped / 0 failed | not re-run this phase (read-only audit; no code changed) |

No external API call, no database write, no test run occurred in this phase.

---

## 3. Full Market Sweep (all 38 markets, not just the 14)

`TrainingPreflightService.check()` was run against every market in `prediction_markets` this
audit. Results fall into exactly three buckets:

### Bucket A — 14 genuinely-trained football markets (real labels, 652–824 observations each)

All 14 fail on the identical 3 checks:
- `training_inference_feature_parity` — FAIL
- `required_feature_coverage_acceptable` — FAIL
- `dataset_provenance_persisted` — FAIL

All other 9 checks (`market_exists`, `feature_manifest_declared`,
`sufficient_labeled_observations`, `labels_valid`, `temporal_reference_present`,
`temporal_split_valid`, `feature_versions_known`, `intelligence_feature_leakage_safe`,
`dataset_reproducible`) **pass** for every one of the 14.

### Bucket B — 5 heuristic-placeholder football markets + `football.match_result` (deprecated)

`first_half_both_teams_to_score`, `first_half_goals`, `first_half_winner`, `second_half_winner`,
`match_result`: never trained, `prediction_outcomes = 0` for each (confirmed unchanged from
Milestone 17/19). `DatasetBuilder.build()` produces an empty sample set, so these fail on:
- `sufficient_labeled_observations` — FAIL (0 samples, minimum 30)
- `temporal_reference_present` — FAIL (vacuously, 0 of 0)
- `temporal_split_valid` — FAIL (`InsufficientSamplesForSplitError`, need >= 2 samples)
- `dataset_provenance_persisted` — FAIL (same as Bucket A)

Notably, these 5 markets' `feature_market_mappings` require **zero** gated
lineup/transfer/news features (confirmed directly: `football.first_half_both_teams_to_score`'s
only required feature is `football.fixture.form_shots_on_target_diff_last5`, a core feature with
real historical coverage; `football.match_result` requires only that same single core feature).
Verified live: for these 5, `training_inference_feature_parity` and
`required_feature_coverage_acceptable` **pass** (vacuously — there is nothing gated to fail on).
**This means these 5 markets have the opposite problem from Bucket A: no parity issue at all, but
zero training data, ever.** A future backfill of ordinary match-outcome data (not gated
intelligence — this bucket needs none) could in principle make one of these five READY without
touching any provenance-sensitive feature at all. That backfill was out of scope for this
read-only audit and is not attempted here.

### Bucket C — 24 basketball/baseball/table_tennis markets

Confirmed (spot-checked `basketball.moneyline`, cross-referenced against the Milestone 17 finding
that 0 non-football markets have ever had a Champion or any `Prediction`/`PredictionOutcome`
rows): all 24 fail identically to Bucket B — `sufficient_labeled_observations`,
`temporal_reference_present`, `temporal_split_valid`, `dataset_provenance_persisted` — because
these sports have real fixtures ingested but zero downstream trainable data (no provider/feature
calculator work has ever been done for them; out of scope per the existing product roadmap,
unrelated to Milestone 20).

**Across all 38 markets: 0 READY.**

---

## 4. Per-Market Parity Matrix (Bucket A, the only markets with a genuine parity question)

Reused directly from the Milestone 19 audit (§4–§6), re-verified live this audit and unchanged:

| Market | Required gated features | Training coverage (gated) | Live coverage (gated) | Historical reconstructability | Resolution status |
|---|---|---|---|---|---|
| away_clean_sheet / home_clean_sheet | lineup×2, transfer×2, news.clean_sheet_impact×2 | 0% | 0% | NO | genuine blocker |
| away_win_to_nil / home_win_to_nil | lineup×2, transfer×2, news.clean_sheet_impact×2 | 0% | 0% | NO | genuine blocker |
| away_team_total_goals / home_team_total_goals | lineup×2, transfer×2, news.goal_impact×2 | 0% | 0% | NO | genuine blocker |
| total_goals_over_under (+4 threshold variants) | lineup×2, transfer×2, news.goal_impact×2 | 0% | 0% | NO | genuine blocker |
| both_teams_to_score | lineup×2, transfer×2, news.btts_impact×2 | 0% | 0% | NO | genuine blocker |
| correct_score | lineup×2, transfer×2 (no news) | 0% | 0% | NO | genuine blocker |
| match_winner | lineup×2, transfer×2 (no news) | 0% | 0% | NO | genuine blocker |

Every row: **genuine blocker, requires real live-scheduled data, cannot be resolved without
fabrication.** No row is safely resolvable by a code or schema change.

---

## 5. Root Cause — Why This Is Structural, Not a Defect

Traced end to end, re-verifying every link in the chain this audit (all code citations
independently re-read, not assumed from the Milestone 19 report):

1. `modules/intelligence/application/news_provenance.py:70-71` — `VERIFIED_PRE_MATCH` can only
   be produced when `trigger is SyncTrigger.LIVE_SCHEDULED`. Confirmed unchanged.
2. `modules/predictions/application/windowed_feature_engineering_service.py` — both
   `LineupContinuityCalculator` and `TransferActivityCalculator` only write a feature value when
   the underlying `Lineup`/`Transfer` row is already `VERIFIED_PRE_MATCH` (Milestone 19 §9-10,
   re-confirmed by grep this audit — no second code path exists).
3. `LIVE_SCHEDULED` can only fire from the real-time Celery Beat schedule
   (`modules/ingestion/infrastructure/celery/beat_schedule.py`), which requires the sync to run
   **while a fixture is still upcoming** — i.e., before its kickoff.
4. Every one of the 14 trained markets' ~652–824 historical observations comes from fixtures that
   **already kicked off and completed** before this platform's `LIVE_SCHEDULED` structured-intel
   sync (added in Milestone 5) or scheduled news sync (added in Milestone 10) ever ran against
   them, or before `NEWS_SYNC_ENABLED`/live syncing was ever turned on for any sustained period
   (`intelligence_sync_runs` shows 23 runs, all `trigger='manual'`, confirmed unchanged this
   audit — zero `LIVE_SCHEDULED` runs have ever executed in this `dev.db`).
5. Therefore, for these specific already-completed fixtures, there is no way — now or ever — to
   produce a genuinely-timestamped, pre-kickoff-verified lineup, transfer, or news observation.
   The window in which that information could have been legitimately captured has permanently
   closed. This is not a temporary data-availability gap that a backfill script could close (a
   backfill can only inspect what a provider now returns for a completed match, which is
   necessarily post-match knowledge, and Milestone 5's provenance classifier correctly refuses to
   call that `VERIFIED_PRE_MATCH` — confirmed unchanged: `scripts/backfill_squad_intelligence.py`
   still passes `trigger=SyncTrigger.BACKFILL` explicitly, lines unchanged from Milestone 19).

**Conclusion: no code change available in this session can move any of the 14 Bucket A markets to
READY.** The only way forward for these specific markets is either (a) real calendar time passing
with live sync genuinely running against genuinely-upcoming fixtures, accumulating an entirely new
training set going forward (an operational decision requiring explicit authorization per §19,
outside a single coding session's control), or (b) a deliberate, separately-authorized product
decision to reclassify which features are genuinely required per market — which Milestone 16 and
this milestone's own §5/§1 explicitly forbid doing merely to satisfy the gate, and which this
audit does not recommend attempting as a way to manufacture a training-ready market.

---

## 6. Answering the 8 Required Audit Questions

**1. Why each M19 market fails.** Bucket A (14 markets): `training_inference_feature_parity` +
`required_feature_coverage_acceptable` both fail because 6 gated features (lineup×2, transfer×2,
news×0-2) have 0% historical coverage — confirmed via `feature_values_offline` (0 rows for any
gated key) and direct inspection of every historical `Prediction.feature_snapshot` (0 occurrences
across ~11,000 rows). `dataset_provenance_persisted` fails for all 14 (and for every market in
the catalog) because `DatasetRepositoryPort` is wired in-memory-only by design (ADR-008).
Bucket B/C (24 markets): `sufficient_labeled_observations` fails because zero
`PredictionOutcome` rows exist for any of them.

**2. Which failures are genuine blockers.** All of Bucket A's parity/coverage failures — genuine,
data-availability blockers, not code defects. Bucket B/C's zero-observations failures are also
genuine (there is no training data to build a dataset from), though for a structurally different
and, for Bucket B, potentially much simpler reason (ordinary match-outcome backfill, no gated
intelligence needed).

**3. Which failures can be resolved safely.** Exactly one, platform-wide:
`dataset_provenance_persisted` — implementing a real `SqlAlchemyDatasetRepository` against the
already-existing `datasets` table (schema unchanged, no migration needed) would flip this one
check to PASS for any market whose `Dataset` gets persisted. It would **not**, by itself, make any
Bucket A market READY, since the parity/coverage checks are independent and still fail. This is
the only "safely resolvable by code" item this audit identified anywhere in the 38-market sweep.

**4. Which failures require historical data.** All of Bucket A (needs historical
`VERIFIED_PRE_MATCH` lineup/transfer/news, impossible per §5). Bucket B's `match_result` and the
4 other heuristic markets need historical match-outcome data only (no gated intelligence) — this
is a materially easier, different kind of gap, out of Milestone 20's stated scope (parity, not
raw-data backfill for never-trained markets), and `match_result` is additionally `deprecated`.

**5. Which failures require live scheduled data.** All of Bucket A, permanently, for any *new*
fixture going forward (not retroactively — see §5). This is the only path that could ever move a
Bucket A market toward READY, and it takes real elapsed time with `NEWS_SYNC_ENABLED=true` and the
structured-intel Celery Beat schedule genuinely running against genuinely-upcoming fixtures.

**6. Which failures cannot be resolved without fabrication.** All of Bucket A's parity/coverage
failures, for the existing historical fixture set — see §5's closed-window argument. Any attempt
to backfill `VERIFIED_PRE_MATCH` for an already-completed fixture, or to make the 6 gated features
optional purely to satisfy the gate, would be fabrication or gate-weakening, both explicitly
forbidden by this milestone's §1 and by Milestone 16's standing instruction.

**7. Which market is the safest first M20 candidate.** **None, today.** If forced to rank for
*future* readiness once live sync has run for a while, `football.correct_score` and
`football.match_winner` have the smallest gated-feature footprint (4 required gated features,
lineup+transfer only, no news) of the 14, making them the shallowest climb once real
`VERIFIED_PRE_MATCH` data starts accumulating — but this is a forward-looking observation, not a
current recommendation, since neither is closer to READY today than any other Bucket A market
(all are at literally 0% gated coverage).

**8. Whether any code/schema changes are actually required.** One optional, non-blocking change
identified (§6.3, `dataset_provenance_persisted`) — genuinely safe, but insufficient on its own to
produce a single READY market. No other code or schema change would legitimately change today's
outcome without violating an explicit prohibition in this milestone's governing rules.

---

## 7. Recommendation

This audit's own evidence points toward **Milestone 20 STATE C (TRAINING BLOCKED)** as the honest,
final outcome — 0 of 38 markets can legitimately reach `TrainingPreflightService` READY today, and
none of Bucket A's blockers are resolvable within this session without violating an explicit
prohibition (fabricated provenance, weakened required-feature gates, backdated availability
timestamps). STATE C is explicitly declared valid by this milestone's own governing rules (§12,
§26).

Two paths are available from here, and this document stops before choosing either, per the
master prompt's Phase 0 protocol:

**(a)** Skip straight to `docs/milestone20_blocked_training_report.md` (§12) declaring STATE C,
with no further implementation — the honest, minimal-risk close to the milestone.

**(b)** Additionally implement the one identified safe, non-blocking fix (§6.3 — a durable
`SqlAlchemyDatasetRepository`, closing the `dataset_provenance_persisted` gap platform-wide) before
writing the blocked-training report, so that gap is at least closed for whenever real data does
arrive — understanding explicitly that this does **not** change today's READY=0 outcome for any
market.

**STOPPING HERE. Waiting for explicit direction between (a) and (b) — or any other instruction —
before any implementation begins.**
