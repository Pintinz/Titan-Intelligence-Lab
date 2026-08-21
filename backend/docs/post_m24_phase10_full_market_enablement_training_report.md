# POST-M24 Phase 10 — Full Market Enablement + First Legitimate Model Training

**Date:** 2026-08-16
**Scope:** Independently re-verify all 43 catalogued prediction markets against live `dev.db`,
classify every one into exactly READY_FOR_TRAINING / BLOCKED_BY_DATA / BLOCKED_BY_ARCHITECTURE /
UNSUPPORTED, investigate the two open architectural questions from prior sessions (`dataset_provenance_persisted`
always failing; `lineup_continuity`/`transfer_activity` at 0% coverage), and train the first market
to reach READY_FOR_TRAINING if any does. No fabrication, no gate-weakening, no Celery Beat.

---

## 1. Executive Summary

**0/43 markets are legitimately READY_FOR_TRAINING. No training was performed.**

This is not a new finding — it independently reconfirms, via a fresh live `TrainingPreflightService`
run against every one of the 43 catalogued markets (not just the 14 football candidates prior
sessions focused on), the same conclusion this repository's own same-day
[`post_m24_phase9b_training_readiness_revalidation.md`](post_m24_phase9b_training_readiness_revalidation.md)
already reached for football. This session extends that verification to basketball, baseball, and
table tennis, and closes out the two open investigation threads (dataset persistence, lineup/transfer
coverage) with root causes rather than open questions.

Every blocker is structural, not a code defect this session is authorized to fix:

- **18 football markets** (14 "candidate" + 4 "insufficient data" + the deprecated `match_result`):
  blocked by a genuine, unresolved data deficit — `lineup_continuity`/`transfer_activity` features
  have 0% real coverage anywhere in `dev.db`, and the only legitimate path to real coverage is a
  live, near-kickoff scheduled sync, which requires Celery Beat — explicitly prohibited this phase.
- **18 basketball + baseball markets**: blocked because no prediction was ever generated for these
  sports — `predictions`/`prediction_outcomes` are 100% football (12,436/12,436 and 11,194/11,194).
  This is `task #158` (`Register api_basketball/api_baseball providers + feature calculators`),
  already tracked as pending in the standing task list — a genuine architecture gap, not a data
  volume problem to backfill.
- **6 table tennis markets**: no provider exists for this sport in the codebase at all. Per the
  Phase 10 instruction itself, this sport correctly stays **UNSUPPORTED**.

No code was changed this session. No training ran. Champion set, predictions, prediction outcomes,
datasets, and calibration reports are byte-for-byte unchanged from the session's own opening
snapshot.

---

## 2. Runtime + Safety Verification (Phase A)

| Component | Status |
|---|---|
| Frontend | UP — port 5173 |
| Backend | UP — port 8000 |
| Redis | UP — port 6379 |
| Backend → Database | Confirmed reachable |
| Celery Beat | **STOPPED** (was found running as leftover standing infra at session start; stopped per this phase's explicit requirement — no scheduled calibration/retraining/promotion could execute during this session) |
| Celery Worker | Left running (not required this session — no training executed) |

**Pre-mutation baseline** (unchanged at time of writing this report — verified identical, see §9):

| Table | Count |
|---|---|
| `prediction_markets` | 43 (42 `production` + 1 `deprecated`: `football.match_result`) |
| `models` | 47 (candidate=14, champion=19, retired=14) |
| `predictions` | 12,436 (100% football) |
| `prediction_outcomes` | 11,194 (100% football) |
| `datasets` | 24 (all `status='draft'`, all `samples=[]` — empty placeholders, see §5) |
| `calibration_reports` | 0 |
| `lineups` | 4 |
| `transfers` | 308 |
| `feature_values_offline` | 108,230 rows total; **0** for `lineup_continuity`/`transfer_activity` keys |

---

## 3. Market Audit (Phase B) — Full 43-Market Ground Truth

Ran the live `TrainingPreflightService.check()` (`modules/predictions/application/training_preflight_service.py`)
against every one of the 43 catalogued `market_key`s directly against `dev.db` — not trusted from
any prior report.

| Cluster | Markets | Blocking checks | Classification |
|---|---|---|---|
| Football — 14 "candidate" markets (correct_score, both_teams_to_score, total_goals_over_under ×5, home/away_win_to_nil, home/away_team_total_goals, home/away_clean_sheet, match_winner) | 14 | `training_inference_feature_parity`, `required_feature_coverage_acceptable`, `dataset_provenance_persisted` | **BLOCKED_BY_DATA** |
| Football — 4 "insufficient data" markets (first_half_both_teams_to_score, first_half_goals, first_half_winner, second_half_winner) | 4 | above + `sufficient_labeled_observations`, `temporal_reference_present`, `temporal_split_valid` | **BLOCKED_BY_DATA** |
| Football — `match_result` (deprecated) | 1 | `sufficient_labeled_observations`, `temporal_reference_present`, `temporal_split_valid`, `dataset_provenance_persisted` | **BLOCKED_BY_DATA** (also deprecated — superseded by `match_winner`, not a live candidate regardless) |
| Basketball (all 12 markets) | 12 | `sufficient_labeled_observations`, `temporal_reference_present`, `temporal_split_valid`, `training_inference_feature_parity`, `required_feature_coverage_acceptable` | **BLOCKED_BY_ARCHITECTURE** |
| Baseball (all 6 markets) | 6 | same as basketball | **BLOCKED_BY_ARCHITECTURE** |
| Table tennis (all 6 markets) | 6 | same as basketball | **UNSUPPORTED** (no provider exists for this sport) |

**Total: 0/43 READY_FOR_TRAINING.**

Every non-listed check (`market_exists`, `feature_manifest_declared`, `labels_valid`,
`feature_versions_known`, `intelligence_feature_leakage_safe`, `dataset_reproducible`, and — for the
14 football candidates only — `sufficient_labeled_observations`/`temporal_reference_present`/
`temporal_split_valid`) **passes** for the football candidate markets, which have real, substantial
labeled history (653–828 samples per market). Basketball/baseball fail those same checks because
they have **zero** labeled observations, not an insufficient number.

---

## 4. Pre-Match Intelligence Investigation (Phase C) — Root Cause, Not a Defect

Traced `lineup_continuity`/`transfer_activity` end-to-end:

```
lineups table (4 rows) / transfers table (308 rows)
      ↓
LineupContinuityCalculator / TransferActivityCalculator
  (modules/predictions/application/windowed_feature_engineering_service.py:340-367, 534-558)
      ↓
FeatureStoreService.write("football.fixture.{home,away}_lineup_continuity" / "..._transfer_activity", ...)
      ↓
feature_values_offline — confirmed 0 rows for these 4 feature keys, out of 108,230 total offline rows
```

**Root cause, confirmed directly against `dev.db`:**

1. Only **4** `lineups` rows and **308** `transfers` rows exist in the entire database, against
   7,386 fixtures / 11,194 labeled outcomes. Even under a maximally favorable classification, this
   is nowhere close to the volume needed to clear `required_feature_coverage_acceptable`'s 50%
   threshold.
2. The calculators' own leakage-safety design (Milestone 5/6/7, `LineupRepositoryPort`/
   `TransferRepositoryPort`, provenance-classified `availability_classification`) means only records
   that are genuinely `VERIFIED_PRE_MATCH` may contribute. The only code path that produces that
   classification is a **live, near-kickoff scheduled sync** (`LIVE_SCHEDULED` trigger,
   `LINEUP_PREMATCH_WINDOW_MINUTES` gate — Milestone 5.3), which runs exclusively off Celery Beat.
3. Celery Beat was explicitly required to stay stopped this entire session. This is a real,
   deliberate constraint of this phase's instructions, not an oversight — and it is precisely the
   mechanism that would let real coverage accumulate over time.

**This is not a bug to fix.** The architecture correctly refuses to fabricate or backdate lineup/
transfer availability. Historical reconstruction is explicitly restricted to `BACKFILL`
classification (Milestone 14/15's `HistoricalFeatureReconstructionService`) precisely so post-match-
only data is never claimed as pre-match knowledge — and BACKFILL-classified lineup/transfer data
does not exist either, because no legitimate historical lineup/transfer source has been backfilled
for these two entity types (unlike team_statistics, which Phase 9 did backfill from
football-data.co.uk). Closing this gap requires either (a) letting the existing live-sync
architecture run for real over multiple matchdays, or (b) a genuine, licensed historical lineup/
transfer data source being sourced and backfilled — both are data-acquisition efforts outside this
session's scope, not code defects.

**No code was changed for this phase.**

---

## 5. Dataset Provenance Investigation (Phase D) — Root Cause, Not a Defect

Traced the full write path:

- `DatasetBuilder.build()` (`modules/predictions/application/dataset_builder_service.py`) — confirmed
  **read-only**; never calls `.save()`/`.upsert()` on any repository. It only ever *constructs* an
  in-memory `Dataset`.
- `DatasetRegistryService.register()` (`modules/predictions/application/dataset_registry_service.py:36-37`)
  is the only method that persists a dataset (`self.datasets.upsert(dataset)`, backed by the real
  SQL `SqlAlchemyDatasetRepository` from Milestone 20).
- Grepped every call site of `DatasetRegistryService`/`.register(`: the **only** production code
  path that ever calls it is `ScheduledRetrainingOrchestrator._build_validate_approve_dataset()`
  (`modules/predictions/application/scheduled_retraining_orchestrator.py`) — invoked exclusively as
  step one of an actual retraining attempt.

**Root cause:** `dataset_provenance_persisted` correctly fails for every one of the 14 football
candidate markets because **no real training/retraining run has ever executed for them** in this
`dev.db`. The 24 existing `datasets` rows are empty (`samples=[]`, `status='draft'`) placeholders
from a prior one-off/testing batch — none of them represent a genuine build-validate-approve cycle
for the markets currently being evaluated, which is why the check (which requires a real persisted
row for that specific `market_id`) still fails for those markets.

**This gate is working as designed, not broken.** Per the orchestrator's own lifecycle, this check
is meant to self-satisfy as the natural first step of a legitimate training run — not something to
pre-populate out of band. Manually calling `DatasetRegistryService.register()` outside of a real
training attempt, just to make this check pass, would be exactly the "create an empty dataset merely
to satisfy the check" behavior this phase's instructions explicitly forbid. No such action was taken.

**No code was changed for this phase.**

---

## 6. Market-Specific Feature Enablement (Phase E) — Not Attempted

Football's 18 markets already have full resolver/feature/dataset-builder/training-adapter/inference-
adapter/evaluation/registration wiring (Milestones 1–20) — the blocker is exclusively the data
deficits in §4/§5, not missing wiring. No football feature-enablement work was needed.

Basketball/baseball feature enablement (task #158/#159) was **not attempted this session**. It is a
substantial, multi-part architecture build — registering `api_basketball`/`api_baseball` providers,
building sport-specific feature calculators, wiring market seeding, and validating the full
resolver → feature → dataset → training chain end to end for two new sports — not a fix that fits
safely within a single read-verify-report session, and the Phase 10 instructions are explicit that
no market should be forced toward readiness. It remains correctly tracked as pending (`task #158`,
`#159`, `#483`).

Table tennis correctly has no provider and stays **UNSUPPORTED** per this phase's own instruction.

---

## 7. Training/Inference Parity (Phase F)

Already fully audited in Phase 9B (§5/§7 of that report) for the stat-differential feature family:
one calculator, one code path (`compute_and_write`), shared identically by training backfill and
live reconciliation — structurally leakage-safe and parity-safe by construction, re-confirmed
unchanged this session.

The actual parity failure blocking the 14 football candidates is `lineup_continuity`/
`transfer_activity` being entirely absent from every training sample (§4) — not a training/inference
divergence, a total absence on both sides equally.

---

## 8. Dataset Construction / Final Preflight / Training (Phases G–L)

Per the Phase 10 instructions' own final rule:

> "If no market reaches READY_FOR_TRAINING: DO NOT TRAIN. Report exact blockers."

**0/43 markets reached READY_FOR_TRAINING.** No dataset was built via `DatasetBuilder` for training
purposes (building one now, with no market ready to consume it, would serve no legitimate purpose).
No training ran. No model was evaluated. No model was registered. No Champion was touched.

---

## 9. Database Safety Verification

| Check | Before | After | Result |
|---|---|---|---|
| `models` | 47 (19 champion / 14 candidate / 14 retired) | 47 (19 / 14 / 14) | Unchanged |
| `predictions` | 12,436 | 12,436 | Unchanged |
| `prediction_outcomes` | 11,194 | 11,194 | Unchanged |
| `datasets` | 24 (all draft, empty) | 24 (all draft, empty) | Unchanged |
| `calibration_reports` | 0 | 0 | Unchanged |
| `prediction_markets` | 43 | 43 | Unchanged |

This session performed **zero writes** — every action was a read-only query or a live (read-only)
`TrainingPreflightService.check()` call.

---

## 10. Tests

No code was changed this session, so no new tests were written and the full regression suite was not
re-run (nothing changed that could regress). The most recent full-suite result on record in this
repository's own reports (Phase 9B) was **2,423 passed / 58 skipped / 0 failed**.

---

## 11. Exact Remaining Blockers (Carried Forward)

1. **`lineup_continuity`/`transfer_activity` — 0% real coverage, universal across all 18 football
   markets that require them.** Resolves only via real, live-scheduled sync accumulating genuine
   `VERIFIED_PRE_MATCH` records over time (Celery Beat, out of scope this session), or a genuine
   licensed historical backfill source for lineups/transfers (not yet sourced).
2. **`dataset_provenance_persisted`** — self-resolving. Will pass automatically as step one of the
   first real, authorized training run for a market once its other blockers clear. Not a defect.
3. **Basketball/baseball (18 markets)** — zero real predictions/outcomes because provider
   registration + feature-calculator wiring for these sports was never built (`task #158`, `#159`).
   A genuine multi-milestone architecture effort, not a data-fix.
4. **Table tennis (6 markets)** — no provider exists; correctly `UNSUPPORTED`.

---

## Final Status

```
RUNTIME: frontend UP, backend UP, redis UP, celery beat STOPPED (per phase requirement)
MARKETS: 0/43 READY_FOR_TRAINING — 18 BLOCKED_BY_DATA (football), 18 BLOCKED_BY_ARCHITECTURE (basketball/baseball), 6 UNSUPPORTED (table_tennis), 1 deprecated (football.match_result, also BLOCKED_BY_DATA)
FIRST TRAINED MARKET: none — no market reached READY_FOR_TRAINING
DATASET: not built (no ready market to build for)
DATASET HASH: n/a
TRAINING ROWS: n/a
FEATURES: n/a
LABELS: n/a
TRAINING-INFERENCE PARITY: n/a (no training attempted)
DATASET PROVENANCE: gate correctly failing — self-resolves at first real training run, not a defect (see §5)
LEAKAGE: n/a (no dataset built)
TEMPORAL VALIDATION: n/a (no dataset built)
PROVENANCE: n/a (no dataset built)
MODEL: none trained
MODEL HASH: n/a
EVALUATION: n/a
CHAMPION: unchanged — 19 champions, byte-for-byte identical to session start
OTHER MARKETS: all 43 classified exactly one of READY_FOR_TRAINING/BLOCKED_BY_DATA/BLOCKED_BY_ARCHITECTURE/UNSUPPORTED (see §3)
DATABASE MODIFIED: NO
DATABASE DELTA: zero rows changed in any table
EXTERNAL API CALLS: 0
GEMINI CALLS: 0
KAGGLE CALLS: 0
BACKEND TESTS: not re-run (no code changed); last full-suite result on record: 2,423 passed / 58 skipped / 0 failed
REGRESSIONS: none (no code changed)
CELERY BEAT: stopped for the duration of this session, per phase requirement
CALIBRATION: none run
RETRAINING: none run
REPORT: backend/docs/post_m24_phase10_full_market_enablement_training_report.md
```
