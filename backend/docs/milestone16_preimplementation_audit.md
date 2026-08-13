# Milestone 16 Pre-Implementation Audit — Training Data Reconstruction & Quality Audit

**Status: READ-ONLY.** No production code was modified. No migration was created. No model was
trained (`.fit()` was never called). No writes were made to `dev.db` — every finding below comes
from either static source-code reading or read-only SQL against `dev.db` (via `?mode=ro`, or via
`DatasetBuilder.build()`, which is itself a pure read — confirmed by direct inspection: it never
calls `.upsert()`/`.record()`/`session.commit()`). `NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED`
remain `false`; no RSS, Gemini, or other external API was contacted.

## 1. Current Training Pipeline (traced from source, not assumed)

```
historical fixture (fixtures table, status='completed')
  -> scripts/backfill_both_teams_to_score_training_data.py::main()
       -> resolves real outcome via MARKET_OUTCOME_RESOLVERS["football.both_teams_to_score"]
       -> (Milestone 15) HistoricalFeatureReconstructionService.publish_for_fixture(...)
          before reading the snapshot (no-op today — see §2)
       -> reads REQUIRED_FEATURES/OPTIONAL_FEATURES from feature_values_offline via a local
          `_latest_feature_value` helper (raw SQL, entity_id = dashed fixture UUID)
       -> constructs a real Prediction (feature_snapshot=dict, status=DRAFT) and a real
          PredictionOutcome (actual_value from the resolver, error=0.0/1.0)
  -> modules/predictions/infrastructure/persistence/repositories.py
       SqlAlchemyPredictionRepository.record / SqlAlchemyPredictionOutcomeRepository.record
  -> modules/predictions/application/dataset_builder_service.py::DatasetBuilder.build()
       -> outcomes.list_by_market(market_id, limit) — SqlAlchemyPredictionOutcomeRepository,
          ORDER BY evaluated_at DESC (see §5 — this ordering matters and is not chronological)
       -> for each outcome: predictions.get(outcome.prediction_id)
       -> _label_from_outcome(...) recovers the real training label from
          (target_type, market_key, prediction.value, outcome.actual_value, outcome.error);
          returns None (sample skipped, never fabricated) if it can't be honestly recovered
       -> TrainingSample(features=dict(prediction.feature_snapshot), label=label)
  -> Dataset(samples=[...], statistics=DatasetStatistics(...), lineage=DatasetLineage(...))
  -> modules/predictions/application/dataset_splitter.py::split(samples, strategy)
  -> modules/predictions/application/training_pipeline_service.py::TrainingPipelineService.train()
     [not invoked in this milestone — see Governing Constraints]
```

- **Script:** `scripts/backfill_both_teams_to_score_training_data.py` (the only backfill script
  Milestone 15 wired to historical reconstruction — see `docs/milestone15_preimplementation_audit.md`).
- **Functions:** `DatasetBuilder.build()`, `_label_from_outcome()`, `_compute_statistics()`,
  `_detect_quality_issues()` (all in `dataset_builder_service.py`); `split()` and its 6 strategy
  functions (`dataset_splitter.py`).
- **Repositories:** `SqlAlchemyMarketRepository`, `SqlAlchemyPredictionRepository`,
  `SqlAlchemyPredictionOutcomeRepository` (all `modules/predictions/infrastructure/persistence/repositories.py`).
- **Tables:** `fixtures`, `feature_values_offline`, `predictions`, `prediction_outcomes`,
  `prediction_markets`, `feature_market_mappings`, `models`.
- **Feature keys (real, as of this audit — see §3):** `football.market.overround`,
  `football.fixture.form_shots_on_target_diff_last5`, `football.fixture.form_possession_pct_diff_last5`,
  `football.fixture.form_shots_total_diff_last5`, `football.fixture.form_corners_diff_last5`,
  `football.fixture.form_fouls_diff_last5`. Zero `news.*` keys appear in any actual sample (§8).
- **Target:** `PredictionOutcome.actual_value`/`.error`, recovered via `real_outcome_is_positive`
  (binary classification; this market has no multiclass catalog entry).
- **Market / sport:** `football.both_teams_to_score` / football — the only market Milestone 15
  wired, and therefore the only one this audit can honestly certify or reject.

## 2. Milestone 15 Coverage

**Zero real reconstruction has been executed against `dev.db`.** Confirmed directly:
`docs/milestone15_verification_report.md` §16 states `dev.db`'s on-disk modification time
predates Milestone 15's work, and every one of Milestone 15's 15 tests ran against isolated,
file-based SQLite databases, never `dev.db`. Milestone 15 changed *code only* — it did not run
`scripts/backfill_both_teams_to_score_training_data.py` for real.

Independently re-confirmed in this audit (§7): `dev.db` has exactly **68 `news_events` rows, all
68 classified `UNKNOWN_AVAILABILITY_TIME`, zero `VERIFIED_PRE_MATCH`.** Since
`NewsEvent.is_feature_eligible()` requires `VERIFIED_PRE_MATCH`, even if the Milestone 15 code path
were run for real against `dev.db` today, it would call `publish_for_fixture` for every eligible
fixture and receive `[]` (nothing written) every single time — consistent with, and not
contradicted by, the fact that no real run has occurred. There is no reconstruction coverage to
report by fixture count (eligible / unresolved / excluded / published) because the reconstruction
call has never executed against real data — stating otherwise would be fabrication.

## 3. Training Dataset Availability

A genuine dataset **was** reconstructed in this audit, using `DatasetBuilder.build()` executed
directly (read-only — see the file header note) against `dev.db`, for the one market Milestone 15
wired: `football.both_teams_to_score` (`market_id = ce223db3-3426-4781-abd5-9f249d47ef00`).

| Metric | Value |
|---|---|
| Total rows (trainable samples) | **652** |
| Feature count | 6 |
| Positive rate (label ≥ 0.5) | 0.561 (366 positive / 286 negative) |
| Quality issues flagged by `DatasetBuilder` itself | none (`TOO_FEW_SAMPLES`/`SEVERE_CLASS_IMBALANCE`/`HIGH_MISSING_RATE`/`ZERO_VARIANCE_FEATURE` all absent) |
| `generated_at` range (when the backfill row was written) | 2026-08-02 20:28 → 2026-08-06 04:50 (a 4-day window — confirms every row is backfill-derived, not organically served over time) |
| `data_freshness` range (≈ fixture kickoff, per the backfill script's own field) | 2022-08-05 19:00 → 2026-08-03 17:52 |
| Unique fixtures (source predictions) | 652 (matches sample count exactly — no duplicates, see §4) |
| Unique seasons | 2 |
| Unique teams | 20 |
| Unique leagues | not separately tracked per-row; not computed (would require a join this audit didn't need for the stated deliverables) |

No external API was used to build this. `DatasetBuilder.build()` is read-only by construction.

## 4. Dataset Identity

Canonical identity for this pipeline is **`Prediction.id`** (one row per `PredictionOutcome`,
joined 1:1 back to its `Prediction`) — `subject_ref` (the dashed fixture UUID) plus `market_id` is
the natural key the backfill script's own `list_by_subject` skip-check already uses to prevent a
second `Prediction` for the same fixture/market pair.

- **Duplicate fixture IDs:** none — 652 samples, 652 unique source `Prediction.id` values, 652
  unique fixtures (verified: `n_source_predictions=652, n_unique=652` and `n_subjects=652,
  n_unique_subjects=652`, both computed directly from the reconstructed dataset).
- **Duplicate market/fixture combinations:** none, by the same evidence.
- **Duplicate feature snapshots / duplicate target rows:** not separately hashed in this audit,
  but the missing-rate/mean/std statistics (§3, §14) show no anomalous clustering that would
  suggest wholesale snapshot duplication.
- **Classification: legitimate / clean.** No accidental or unresolved duplicates found for this
  market.

## 5. Temporal Ordering — CONFIRMED DEFECT

`TrainingSample` (`modules/predictions/ports/ml_model.py`) has exactly two fields: `features` and
`label`. **It carries no timestamp.** `dataset_splitter.py`'s own module docstring is explicit:
`HOLDOUT`/`ROLLING_WINDOW`/`WALK_FORWARD`/`TIME_SERIES_SPLIT` "deliberately do not shuffle...
callers are expected to pass samples in ascending chronological order... if that isn't
chronological for a given repository implementation, that's a caller-side ordering concern, not
this module's."

Traced the actual order, end to end:

1. `SqlAlchemyPredictionOutcomeRepository.list_by_market` (repositories.py:236) orders
   `.order_by(PredictionOutcomeModel.evaluated_at.desc())` — **descending**, newest kickoff first.
2. `DatasetBuilder.build()` iterates these outcomes in that exact order and appends to
   `samples: list[TrainingSample]` with no re-sort.
3. `impute_missing`/`detect_outliers`/`select_features` (`preprocessing.py`) are all confirmed
   order-preserving 1:1 transforms (verified directly in source — none re-sort).
4. `TrainingPipelineService.train()` passes this same list straight to `split()`.

**Result: for this market's real dataset, `dataset.samples[0]` is the newest-kickoff fixture and
`dataset.samples[-1]` is the oldest.** `_time_series_split`/`_walk_forward`/`_rolling_window`
(`dataset_splitter.py`) all build `train_fold = samples[:k]` and `test_fold = samples[k:k+step]` —
under the actual (descending) order, every "train" fold is *chronologically newer* than the "test"
fold that follows it in the list. This is the exact inverse of a valid walk-forward/time-series
validation, which must train on the past and evaluate on the future. No feature value leaks
information from the future (each `TrainingSample.features` is an independent, per-fixture
snapshot — see §21), but **any held-out metric produced by `TIME_SERIES_SPLIT`/`WALK_FORWARD`/
`ROLLING_WINDOW`/`HOLDOUT` today would misrepresent real-world forward-looking generalization**,
since the model is being asked to predict older matches from a model fit on newer ones — backwards
from deployment.

**Which strategy does the real production path actually use?** Traced explicitly:
`AutomaticModelSelectionService.select`/`.select_and_register_challenger`
(`model_selection_service.py:126,181`) both default `split_strategy=SplitStrategy.TIME_SERIES_SPLIT`
(not `TRAIN_TEST`), and forward it unchanged into `TrainingPipelineService.train()`.
`ScheduledRetrainingOrchestrator` (the real Celery-triggered production caller) calls
`self.model_selection.select_and_register_challenger(...)` with no `split_strategy` override found
anywhere in that file or in `composition.py` — so the live retraining path **does** use the
time-aware strategy in name, but that strategy is fed data in the wrong order, undermining the
entire reason it was chosen over `TRAIN_TEST`. (`TrainingPipelineService.train()`'s own standalone
default of `SplitStrategy.TRAIN_TEST` is a real, separate finding — see §17's cross-reference — but
is not what the production retraining path actually invokes.)

A prior, independently-run audit track (`docs/milestone3_historical_data_audit.md`, dated 2026-08-11,
different numbering, same repository) reached a compatible earlier finding: "training used a random
shuffle split, not time-based (Milestone 2 finding, unchanged)" for the 14 originally-trained
football Champions. That finding and this one describe two related-but-distinct defects across
time: an earlier random-shuffle default, and (independently reconfirmed here, in the code as it
exists today) a chronological-direction bug in the *currently wired* time-aware strategy. Neither
is fixed as of this audit.

**Explicit rejection per this milestone's requirement:** `SplitStrategy.TRAIN_TEST` (random
shuffle) is correctly *not* the production default in `AutomaticModelSelectionService` today, and
this audit does not recommend it. But `TIME_SERIES_SPLIT` as currently fed **cannot be certified
safe** until the ordering defect in §5 is fixed (re-sort `dataset.samples` ascending by a genuine
timestamp before splitting — `TrainingSample` would need an added timestamp field, or
`DatasetBuilder` would need to sort before discarding it). This is a **blocker** per Mandatory Stop
Condition 14 ("temporal split cannot be applied [safely]").

## 6. Point-in-Time Feature Safety (by category)

| Feature category | Information available before kickoff? | Evidence |
|---|---|---|
| Historical match statistics (form differentials, overround) | Yes, by construction — computed from windowed pre-fixture aggregates (Milestone 6/7's `RollingTeamStatAverageCalculator`/`FixtureFormDifferentialCalculator`), verified leakage-safe in Milestones 4/6/7's own test suites. | Re-verified structurally in §3: these are the only 6 keys actually present in the reconstructed dataset. |
| Team form | Same as above. | Same. |
| Player statistics | Not used by this market at all (not in its `required_features`/`optional_features`). | `market_seeding.py` §229-241. |
| Lineup (`*_lineup_continuity`) | `required_features` per `market_seeding.py`, but **absent from every actual sample** (§3's `feature_keys` list has no lineup key) — meaning the live feature-market contract requires it, but it was never populated for any of the 652 backfilled rows. Consistent with `docs/milestone3_historical_data_audit.md`'s finding of 0.24% lineup coverage. | dev.db: 4 lineup rows total, platform-wide. |
| Injuries | Not in this market's feature contract. Flagged separately as a leakage risk if ever wired (§17). | — |
| Transfers (`*_transfer_activity`) | `required_features` per `market_seeding.py`, same absence-from-samples pattern as lineup. | Same. |
| Odds | Not in this market's feature contract. | — |
| News (`news.football.*_btts_impact`) | `required_features` per `market_seeding.py` **and** `feature_market_mappings` (`is_required=1`, confirmed live in dev.db) — but zero eligible events exist anywhere (§7), so this can never be populated today. | §7, §8, §16. |
| Structured intelligence (general) | Same historically-unverified caveat `docs/milestone3_historical_data_audit.md` raised for `injuries.reported_at` (§17) — not used by this specific market, but a real platform-wide risk if wired elsewhere without the fix that doc recommends. | — |

**Required rule** (`information_available_at < fixture_kickoff`) is enforced, for the one category
that actually has a real point-in-time timestamp mechanism (news), by
`NewsEvent.is_feature_eligible()` + `is_information_available_before_kickoff` — both unmodified
since Milestones 9/10 and re-verified by Milestone 15's own test 03. For the 4 currently-live
feature keys with `required_features=True` but zero presence in any sample (lineup/transfer
activity), the *absence* is honest (optional-at-read-time behavior — see §16) rather than a
fabricated pre-kickoff value, so no leakage exists there; the gap is a coverage problem, not a
provenance problem.

## 7. News Feature Safety

Direct SQL against `dev.db` (read-only):

| Availability classification | Count |
|---|---|
| `VERIFIED_PRE_MATCH` | **0** |
| `UNKNOWN_AVAILABILITY_TIME` | **68** |
| `INVALID` | 0 |
| Total `news_events` rows | 68 |

`HistoricalRelevanceClassification` breakdown (`HISTORICALLY_RELEVANT`, `HISTORICALLY_UNRESOLVED`,
`ENTITY_UNRESOLVED`, `MARKET_UNRESOLVED`, `INSUFFICIENT_PROVENANCE`) was not separately computed
here because it requires running `HistoricalNewsRelevanceEngine.resolve_relevance` per event —
Milestone 13's own 17-test suite and Milestone 14's leakage matrix (A-P) already exhaustively cover
every one of these classifications' correctness at the unit level; re-deriving them against these
same 68 real, already-`UNKNOWN_AVAILABILITY_TIME` rows would not change the one fact that matters
for training readiness: **all 68 are excluded before relevance classification is even reached**,
since `is_feature_eligible()`'s `VERIFIED_PRE_MATCH` check is the first gate.

**Critically verified: `HISTORICALLY_RELEVANT` does not imply feature eligibility.** This is
enforced structurally, not just by convention — `HistoricalFeatureReconstructionService._classify`
(Milestone 14) checks relevance, then separately re-checks `NewsEvent.is_feature_eligible()`, then
separately re-checks the kickoff cutoff; Milestone 14's own test suite (`test_c_...`,
`test_b_article_after_kickoff_...`) directly proves a `HISTORICALLY_RELEVANT`-but-ineligible event
never becomes `NEWS_FEATURE_ELIGIBLE`. Unmodified since Milestone 14; re-confirmed structurally in
this audit's source reading, not re-executed (would only re-derive an already-proven fact).

## 8. News Training Coverage

**Zero.** Confirmed directly from the reconstructed dataset (§3): `feature_count=6`,
`feature_keys` contains no `news.*` entry at all. Every one of the 652 rows has zero news features
— not "some rows have it, some don't" (which `missing_rate` would show for a key that's merely
absent from *some* samples), but the key never appears in *any* sample's `feature_snapshot`,
because `_latest_feature_value` for `news.football.home_btts_impact`/`away_btts_impact` returns
`None` for every one of the 652 fixtures (zero eligible historical news exists, §7).

**"News Intelligence is currently infrastructure-complete but training-data-inactive."** — true
and stated exactly as the spec requires, not embellished.

## 9. Historical Entity Resolution

Verified structurally (Milestones 13/14, re-confirmed by Milestone 15's own tests 07/08, which
this audit re-read rather than re-executed): historical player→team membership is resolved
exclusively via `HistoricalEntityResolutionService.resolve_player_membership`, which chains
`Transfer.effective_date` chronologically. `NewsMarketImpactEngine._resolve_roster` — the one and
only roster-resolution code path used when `historical_reference_time` is supplied — has no
dependency on `Player.team_id` or Knowledge Graph `PLAYS_FOR` edges (structurally absent from the
class, not merely unused). A later transfer does not retroactively change an earlier fixture's
resolved membership (Milestone 15 test 07); a deliberately stale/conflicting `Player.team_id`
field is never consulted (Milestone 15 test 08).

`dev.db` real transfer coverage (from `docs/milestone3_historical_data_audit.md`, re-usable since
`transfers` hasn't changed shape since that audit): 308 transfer rows, real player names/fees, no
`effective_until`/validity-window column (single point-in-time `effective_date` only — sufficient
for the chronological-chain resolution this milestone's services actually use, since that
resolution only needs an ordered sequence of `effective_date` values per player, not a validity
window). Since zero eligible news exists (§7), no player membership resolution has actually been
exercised against real historical news for training purposes yet — this machinery is proven
correct in isolation (Milestones 13/14/15's test suites) but has never processed a real event.

## 10. Fixture Context

Every reconstruction call in the pipeline (`HistoricalFeatureReconstructionService.publish_for_fixture`)
takes the fixture's own `home_team_id`/`away_team_id`/`scheduled_at`, read fresh from that
fixture's own row inside the per-fixture loop — no "current schedule" lookup exists anywhere in
this call chain (verified in `scripts/backfill_both_teams_to_score_training_data.py` and
`docs/milestone15_preimplementation_audit.md` §9). Milestone 15's tests 01/02 (side isolation),
09 (unrelated-team leakage) directly exercise wrong-fixture/wrong-team exclusion. Wrong-player
exclusion is covered by Milestone 14's leakage matrix item L. Wrong-market exclusion is covered by
§11 below.

## 11. Market-Specific Impact

`NewsMarketImpactEngine`/`MARKET_IMPACT_RULES` (Milestone 9, unmodified) remain the sole authority
for which news event types affect which dimension. Verified directly for this market: forward-role
`INJURY`/`SUSPENSION`/`RECOVERY` events map to `news.football.btts_impact` via a distinct rule from
the `goal_impact`/`clean_sheet_impact` dimensions the same event simultaneously contributes to
(`news_market_impact_registry.py`) — `publish_for_fixture` writes all three dimensions when
evidence exists, but this market's `OPTIONAL_FEATURES`/`required_features` only ever reads the two
BTTS-specific keys (verified: Milestone 15 test 11 and the live `feature_market_mappings` row set
in §16 both list only `home_btts_impact`/`away_btts_impact`, never `goal_impact`/`clean_sheet_impact`
for this market). No one-size-fits-all news feature is injected.

## 12. Target Label Quality

- **Exact target field:** `Dataset`/`TrainingSample.label` (float), recovered by
  `_label_from_outcome()` from `PredictionOutcome.actual_value`/`.error` (this market has no
  multiclass catalog entry, so `class_labels` is empty and the binary path —
  `real_outcome_is_positive(market_key, prediction.value, error)` — is always used).
- **Label-generation logic / source:** `MARKET_OUTCOME_RESOLVERS["football.both_teams_to_score"]`
  (a real resolver keyed on `home_score`/`away_score`, wired since before Milestone 9), invoked by
  the backfill script against each fixture's real, provider-sourced final score.
- **Outcome resolution:** `PredictionOutcome.actual_value`/`.error` are written once, at backfill
  time, from that same resolver — never re-derived or mutated afterward for these rows.
- **Missing/invalid/conflicting labels:** `_label_from_outcome` returns `None` (sample silently
  skipped, `continue` in `DatasetBuilder.build()`, never fabricated) whenever the real outcome
  can't be honestly mapped — `PredictionOutcomeRepositoryPort.list_by_market` returned some number
  of outcomes ≥ 652 (not separately counted here) and exactly 652 survived with a valid label; the
  gap, if any, is by design (honest skip), not silent corruption.
- **Duplicate labels:** none beyond what §4 already covers (one outcome per prediction, one
  prediction per fixture/market).
- **Target leakage:** the label is computed from `home_score`/`away_score` — real, final,
  post-match facts, written to `fixtures` only once a fixture reaches `status='completed'` — while
  every feature in `feature_snapshot` is read from `feature_values_offline` at a point that (for
  the 6 keys actually present, §6) is itself pre-computed from windowed pre-fixture aggregates.
  **No target leakage found** for this market's real, currently-populated feature set. (This is
  independent of, and does not fix, §5's split-direction defect — that affects validation
  methodology, not whether any individual feature encodes the label.)

## 13. Class Balance

652 samples: **366 positive (56.1%) / 286 negative (43.9%)** — ratio 1.28:1. Well inside
`DatasetBuilder`'s own `_CLASS_IMBALANCE_ALERT_THRESHOLD` (0.9/0.1); `SEVERE_CLASS_IMBALANCE` was
not flagged. No rebalancing, oversampling, undersampling, or SMOTE was applied or is recommended —
per this milestone's own instruction, this is reported for Milestone 17, not corrected here.

## 14. Missing Data

Computed directly by `DatasetBuilder._compute_statistics` against the real 652-sample dataset:

| Feature | Missing rate | Mean | Std |
|---|---|---|---|
| `football.fixture.form_corners_diff_last5` | 0.3% | 0.0015 | 1.767 |
| `football.fixture.form_fouls_diff_last5` | 0.3% | 0.0037 | 2.816 |
| `football.fixture.form_possession_pct_diff_last5` | 0.3% | -0.0049 | 11.57 |
| `football.fixture.form_shots_total_diff_last5` | 0.3% | 0.0089 | 5.747 |
| `football.fixture.form_shots_on_target_diff_last5` | 0.0% | 0.0000 | 2.949 |
| `football.market.overround` | 0.0% | 0.0599 | 0.0008 |

Missingness is uniformly low (≤0.3%) and structurally expected — each of the four ~0.3%-missing
keys is an *optional* feature in this market's mapping (§16), so a rare fixture with genuinely
absent underlying stat data is expected to skip that one key, not indicative of a provider gap or
leakage-related pattern. No true-zero-vs-missing ambiguity was found: `form_shots_on_target_diff_last5`'s
mean of exactly 0.0000 with 0% missing is a real, symmetric differential statistic (home minus
away), not a masked null. No automatic replacement was performed — per this milestone's own
instruction.

## 15. Feature Versioning

`ModelDefinition.feature_versions` (the `models.feature_versions` JSON column) was checked
directly for every model ever registered against this market:

| `model_key` | `status` | `feature_versions` |
|---|---|---|
| `football.both_teams_to_score.svm` | **champion** | `{}` |
| `football.both_teams_to_score.historical-backfill` | candidate | `{}` |
| `football.both_teams_to_score.heuristic` | retired | `{}` |

**Feature versions are empty for the current live Champion.** This is exactly the condition this
milestone's own §15 instruction calls a training-readiness blocker "unless a deterministic
alternative lineage mechanism already exists." One does, partially: `DatasetLineage`
(`Dataset.lineage.feature_keys` + `Dataset.lineage.source_prediction_ids`) is real and populated —
verified directly in §3's reconstruction (`feature_keys` returned a real, non-empty, sorted tuple;
`source_prediction_ids` returned exactly 652 real, unique `Prediction.id` values) — giving a
deterministic trail from any `Dataset` back to the exact `Prediction` rows and feature keys that
produced it. What this trail does **not** give is a per-*feature* version number (e.g., "which
revision of the `form_shots_on_target_diff_last5` calculation logic produced this value") — so it
is a real but partial alternative, not a full substitute for `ModelDefinition.feature_versions`.
**Classified as a genuine, only-partially-mitigated gap, not fully resolved** — carried into the
readiness matrix (§22) as a caveat, not a hard blocker, given the `DatasetLineage` mitigation.

## 16. Feature-Market Mappings — CONFIRMED PRODUCTION DEFECT

Live `feature_market_mappings` rows for `football.both_teams_to_score` (read directly from
`dev.db`):

| `feature_key` | `is_required` | `weight` |
|---|---|---|
| `football.market.overround` | **1** | 1.0 |
| `football.fixture.form_shots_on_target_diff_last5` | **1** | 0.05 |
| `football.fixture.home_lineup_continuity` | **1** | 1.0 |
| `football.fixture.away_lineup_continuity` | **1** | 1.0 |
| `football.fixture.home_transfer_activity` | **1** | 1.0 |
| `football.fixture.away_transfer_activity` | **1** | 1.0 |
| `news.football.home_btts_impact` | **1** | 1.0 |
| `news.football.away_btts_impact` | **1** | 1.0 |
| `football.fixture.form_possession_pct_diff_last5` | 0 | 0.02 |
| `football.fixture.form_shots_total_diff_last5` | 0 | 0.05 |
| `football.fixture.form_corners_diff_last5` | 0 | 0.05 |
| `football.fixture.form_fouls_diff_last5` | 0 | 0.03 |
| `football.fixture.form_cards_yellow_diff_last5` | 0 | 0.1 |

This matches `market_seeding.py`'s current `MARKETS` spec exactly (line 236-240) — **not stale
data**, this is what the live code registers today.

`FeatureMarketMappingService.resolve_feature_snapshot` (called from
`PredictionContextBuilder.build`, line 122 — the real live-prediction context-building path, traced
directly) raises `MissingRequiredFeatureError` if *any* `is_required=True` mapping is absent from
`available_features`. Traced the exception's full path: `prediction_router.py`'s
`POST /api/v1/predictions/...` handler catches `MarketNotFoundError`, `MarketNotInProductionError`,
and `NoChampionModelError` — **not** `MissingRequiredFeatureError**. No global FastAPI exception
handler exists in `apps/api/main.py`/`composition.py` (confirmed by direct search — none
registered) that would catch it either.

**Consequence, confirmed by direct code tracing (not executed against a live server in this
audit, per the "no production writes/no live requests" constraint):** since `news.football.home_btts_impact`/
`away_btts_impact` are `is_required=True` and zero eligible news exists anywhere (§7), **every live
prediction-generation call for `football.both_teams_to_score` today would raise an uncaught
`MissingRequiredFeatureError`**, propagating as an unhandled server error rather than the honest
"insufficient data" response this codebase already gives for `NoChampionModelError` (task #195,
`docs/` architecture history). This is a genuine, currently-live production defect discovered as a
byproduct of this audit's §16 instruction ("ensure training and live prediction use the same
intended market feature contract") — it is not a training-data problem at all, but it does mean
**training and live serving are currently in *worse* than mismatched states: live serving for this
market is structurally broken, independent of anything Milestone 17 would do.** Per this
milestone's constraints, this is reported, not fixed.

`market_seeding.py` itself already documents the general failure mode in nearby comments for
*other* markets ("would raise `MissingRequiredFeatureError` on every prediction today") — those
other markets correctly mark the same class of feature `is_required=False` for exactly this reason;
`football.both_teams_to_score` was not given the same treatment for its two news keys.

## 17. Data Provider Provenance

Reusing `docs/milestone3_historical_data_audit.md` (2026-08-11, same repository, prior audit track
— re-cited rather than re-derived where its findings concern tables this market doesn't touch, and
independently re-confirmed in §7/§9 where they do):

- `injuries.reported_at` **appears to be a backfilled proxy equal to fixture kickoff time**, not a
  genuine pre-match report timestamp (confirmed by that audit's exact-match sampling). **Not used
  by `football.both_teams_to_score`'s feature contract** (§6) — so it is not a live risk for *this*
  market's dataset, but remains a platform-wide risk if any market wires injury data as a
  point-in-time feature before this is resolved. Flagged, not re-verified independently in this
  audit (no reason to re-sample what a same-repository audit already sampled directly).
- `transfers.effective_date`: single point-in-time timestamp, no validity window — sufficient for
  this milestone's actual use (chronological-chain resolution, §9), insufficient for a genuine
  "was this the active transfer as of arbitrary time T" query without the chain-walk
  `HistoricalEntityResolutionService` already performs.
- `provider` / `sync trigger` / `reconciliation timestamp` for the 6 feature keys this market
  actually uses: sourced from `api_football` (real, active provider, per that same audit's §14),
  computed via Milestone 6/7's windowed calculators at reconciliation time — no direct provenance
  column exists on `feature_values_offline` beyond `as_of`, which the backfill script reads
  correctly (via `_latest_feature_value`'s `ORDER BY as_of DESC LIMIT 1`).

## 18. Join Integrity

The previously-discovered `provider_ref_index.entity_id` vs `fixtures.id`/`teams.id` format
mismatch is **resolved and re-verified live in this audit**: `SELECT COUNT(*) FROM
provider_ref_index WHERE length(entity_id) = 32` returns **0**; all 7,529 rows are canonical
36-character hyphenated UUIDs (`_canonical_entity_id`, `modules/ingestion/infrastructure/persistence/mappers.py`).
That mapper-layer fix's own docstring records that no real application code ever raw-SQL-joins this
column against `fixtures.id`/`teams.id` directly (`EntityReconciliationService._resolve()` always
round-trips through `uuid.UUID()`, hyphen-agnostic) — and confirmed here: **the training
reconstruction path audited in this milestone never touches `provider_ref_index` at all**, so this
historical bug is not a risk to the dataset audited here, resolved or not.

**A new, analogous format footgun was found while writing this audit's own verification queries**
(not a defect in production code, but worth documenting as a real risk for any future ad-hoc
query/tooling): `fixtures.id`/`teams.id`/`predictions.id` are stored **undashed** 32-character hex
(SQLAlchemy's `Uuid` type default for SQLite), while `predictions.subject_ref` (the fixture UUID,
written via the backfill script's own `_dashed()` helper) and `str(SomeValueObjectId)` (e.g.
`str(prediction.id)`, used by `DatasetLineage.source_prediction_ids`) are **dashed**. A naive
`WHERE fixtures.id = predictions.subject_ref` or `WHERE predictions.id IN (<dashed strings>)` join
silently returns zero rows — this audit's own first draft of its dataset-reconstruction verification
script hit exactly this and had to be corrected (`UUID(x).hex` before joining). No production code
path was found doing this incorrectly (every real repository method goes through the ORM's typed
`Uuid` column or `uuid.UUID()`, both format-agnostic) — but it is a real, live, easy-to-hit trap for
any future raw-SQL tooling (training scripts, admin scripts, ad-hoc audits) that isn't using the
ORM. Worth a documented convention, not a code fix, per this milestone's scope.

## 19. Data Coverage

For `football.both_teams_to_score`:

| Metric | Count |
|---|---|
| Total football fixtures (all statuses, per `docs/milestone3_historical_data_audit.md`) | 1,203 |
| Completed football fixtures | 823 |
| Fixtures with a resolved target for this market (= reconstructed sample count) | 652 |
| Fixtures with complete required-core features (6 of 6 present) | 652 (100% of the trainable set — 0.0%/0.3% missing per §14 means effectively every trainable row has every feature) |
| Fixtures with news features | **0** (§8) |
| Fixtures with lineup features | 0 (required in the mapping, §16, but absent from every sample) |
| Fixtures with transfer-activity features | 0 (same) |
| Fixtures with odds features | not in this market's contract |
| Fixtures excluded (completed but no `Prediction`/`PredictionOutcome` for this market) | 823 − 652 = 171 (not separately root-caused in this audit; `docs/milestone15_preimplementation_audit.md` §10 attributes the analogous gap for the whole backfill run to the script's own `skipped_missing_required` counter — most plausibly the same cause here, not independently re-verified) |

Coverage: 652/823 completed fixtures = **79.2%** have a usable training row for this market;
100% of those 652 have complete core (non-news, non-lineup, non-transfer) features.

## 20. Training Sufficiency

- **Observations:** 652 (well above `MIN_TRAINING_SAMPLES = 30`).
- **Positive / negative:** 366 / 286 — both comfortably above any reasonable per-class minimum.
- **Seasons:** 2 — thin. Two seasons is enough to fit a model but thin for validating that it
  generalizes across a season-to-season regime shift (squad turnover, rule changes, etc.).
- **Teams:** 20 — consistent with a single top-flight league's roster size; no diversity across
  competitions was found for this market's dataset.
- **Temporal depth:** `data_freshness` spans 2022-08-05 → 2026-08-03 nominally, but §19's
  fixture-coverage math (823 completed fixtures total, over the football dataset's real window)
  combined with only 2 unique seasons suggests the 652 rows are concentrated, not evenly spread —
  not independently re-verified with a season-by-season histogram in this audit (would be a
  reasonable Milestone 17 pre-flight check, not required to answer this milestone's own question).
- **Feature dimensionality:** 6 real, populated features (plus 2 more that are `is_required=True`
  in the live mapping but never populated — §16) — low-dimensional relative to the market's own
  declared contract.
- **Missingness:** ≤0.3% (§14) — negligible.
- **Market complexity:** binary classification, well-balanced (§13) — the least demanding shape
  this platform's dataset/split infrastructure supports.

**Classification: `TRAINING_READY_WITH_RESTRICTIONS`.** Sample count, balance, and missingness are
genuinely healthy. The restrictions are: (1) §5's split-direction defect must be fixed before any
`TIME_SERIES_SPLIT`/`WALK_FORWARD`/`ROLLING_WINDOW`/`HOLDOUT` result can be trusted; (2) only 2
seasons of temporal depth exist, which bounds how much confidence any validation split (once fixed)
can give about season-to-season generalization; (3) the dataset's own declared feature contract
(§16) includes 4 keys that are formally required but never populated, which either needs the
mapping corrected to match reality or the underlying coverage gap closed before Milestone 17.

## 21. Leakage Audit

Searched for, with results:

- **Post-kickoff timestamps in features:** none found among the 6 real feature keys — all are
  windowed pre-fixture aggregates (Milestone 6/7 calculators), unmodified and previously
  leakage-tested.
- **Current team membership substituting for historical:** not applicable to this market's actual
  feature set (news/entity-resolution machinery exists but has never processed a real event, §9);
  structurally prevented where it is exercised (Milestones 13/14/15 tests).
- **Current standings / future fixture information / future transfers:** not features of this
  market.
- **Post-match statistics / post-match odds / post-kickoff news:** not features of this market;
  news specifically gated by `is_feature_eligible()` + kickoff-cutoff (§6), independently
  structurally verified.
- **Labels accidentally included as features:** no — verified in §12, `feature_snapshot` and
  `PredictionOutcome.actual_value` come from disjoint code paths (feature calculators vs. outcome
  resolvers), and the 6 real feature keys' names/semantics have no overlap with the BTTS outcome.
- **Future-derived rolling statistics / full-season aggregates containing future matches:** not
  independently re-audited at the calculator level in this milestone (out of scope — Milestones 6/7
  already carry this burden and were not touched by Milestone 15 or this audit); no new evidence of
  a defect found.
- **Split-direction defect (§5):** confirmed, real, structural — the one genuine leakage-adjacent
  finding of this audit. Not label/feature leakage in the strict sense (no individual sample's
  features encode a future fact), but a methodological defect that would produce a misleadingly
  optimistic validation metric, which is the practical harm the "no random shuffle" requirement
  exists to prevent in the first place.

**No confirmed data leakage** (in the strict, per-sample sense) was found in this market's actual
feature set. **One confirmed methodological/ordering defect** (§5) was found in the split
infrastructure every future market will inherit.

## 22. Model-Training Readiness Matrix

| Requirement | Status | Evidence | Blocker |
|---|---|---|---|
| Real historical fixtures | ✅ PASS | 652 real, unique, backfill-derived training rows (§3, §4) | No |
| Valid targets | ✅ PASS | Real resolver output, no fabrication, no target leakage found (§12) | No |
| Point-in-time features | ⚠️ PARTIAL | The 6 populated features are structurally pre-kickoff-safe (§6); 2 more (news) are correctly gated but never populate; 2 more (lineup/transfer) are required-but-absent, an honesty gap not a leakage gap | No (for the 6 real features) |
| Historical entity resolution | ✅ PASS (untested against real data) | Transfer-chain-only, proven correct in Milestones 13/14/15 tests; never yet exercised against a real event (§9) | No |
| News provenance | ✅ PASS | `VERIFIED_PRE_MATCH` correctly unreachable from `BACKFILL`/`ADMIN_MANUAL`; 0/68 real events eligible (§7) | No |
| Market-specific news | ✅ PASS | BTTS dimension correctly isolated from goal/clean-sheet (§11) | No |
| Feature versioning | ⚠️ PARTIAL | `ModelDefinition.feature_versions = {}` for the live Champion; `DatasetLineage` gives a partial deterministic alternative (§15) | No (mitigated, not resolved) |
| Duplicate control | ✅ PASS | 0 duplicates found (§4) | No |
| Missingness | ✅ PASS | ≤0.3% across all 6 real features (§14) | No |
| Time-based split | 🔴 FAIL | `dataset.samples` is fed to the splitter in descending-chronological order; every time-aware strategy's train/test direction is inverted (§5) | **Yes** |
| Leakage control | ✅ PASS | No per-sample feature/label leakage found (§21) | No |
| Dataset size | ✅ PASS | 652 ≫ `MIN_TRAINING_SAMPLES=30`; balanced (§13, §20) | No |
| Class balance | ✅ PASS | 56.1% / 43.9% (§13) | No |
| Provider provenance | ✅ PASS (for features used) / ⚠️ PARTIAL (platform-wide `injuries.reported_at` risk, not used here) | §17 | No (for this market) |
| Production/live parity | 🔴 FAIL | `football.both_teams_to_score`'s live feature contract requires 2 news + 2 lineup/transfer keys that never populate; the news ones raise an **uncaught `MissingRequiredFeatureError`** on every live generation attempt today (§16) | **Yes (separately from training)** |

## Summary of Blockers

1. **§5 — Split-direction defect.** `TIME_SERIES_SPLIT`/`WALK_FORWARD`/`ROLLING_WINDOW`/`HOLDOUT`
   currently receive samples in descending-chronological order with no re-sort anywhere in the
   pipeline, inverting train/test direction. Must be fixed (add a real timestamp to
   `TrainingSample`, or sort ascending in `DatasetBuilder`/`TrainingPipelineService` before
   splitting) before any held-out metric from Milestone 17 can be trusted.
2. **§16 — Live feature-contract mismatch (found, not caused, by this audit).** Two of
   `football.both_teams_to_score`'s `required_features` (`news.football.home_btts_impact`/
   `away_btts_impact`) can never be populated given zero eligible news exists, and the resulting
   `MissingRequiredFeatureError` is uncaught by `prediction_router.py`, unlike the honest handling
   already given to `NoChampionModelError`/`MarketNotInProductionError`. This is a live-serving
   defect, independent of Milestone 17, but directly bears on "does training data match the
   production feature contract" — today, it structurally cannot, for 2 of 8 required keys.

Neither blocker was fixed in this milestone, per its own read-only, no-training constraint. Both
are reported for explicit approval before any further work.

## STOP

Per this milestone's governing process: **read-only audit complete.** No code was modified beyond
this document. No migration was created. No model was trained. No `dev.db` write occurred.
`NEWS_SYNC_ENABLED`/`NEWS_BACKFILL_ENABLED` remain `false`. No external API was contacted.

**MILESTONE 16 PHASE 1 AUDIT COMPLETE — WAITING FOR EXPLICIT APPROVAL.**
