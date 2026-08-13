# Milestone 8 Verification Report — Optional Structured-Intel Wiring on Heuristic Markets

## 0. Scope and governing rule

Both Milestone 6 and Milestone 7 explicitly flagged the same deferred item: wiring
`LineupContinuityCalculator`'s and `TransferActivityCalculator`'s features into the
heuristic-placeholder markets they deliberately excluded, because those markets are served by a
**live formula predictor** that reads `FeatureMarketMapping` fresh at inference time — a real
production-serving concern the 14 trained markets don't have (their `required_features` only
affects a future retrain). Both reports called this "needs its own dedicated verification pass, not
a byproduct of this milestone." This is that dedicated pass.

No user-supplied M8 spec accompanied this milestone. Scope was determined by reading M4–M7
documentation and the existing implementation, confirmed with a targeted research investigation
into the live-serving path before any code was written, and presented to the user as an
implementation plan before implementation began. Governing principles carried over unchanged: NO
DATA DUMPING. NO FABRICATION. NO DATA LEAKAGE. NO SPOOFED PROVENANCE. NO TRAINING DURING INFERENCE.
NO UNVALIDATED MODEL PROMOTION. A feature that cannot prove when its information became available
must NOT influence a prediction.

## 1. What was built

`football.fixture.{home,away}_lineup_continuity` and `{home,away}_transfer_activity` (Milestones
6/7, unchanged) are now also mapped, as **optional** features with conservative weights, to the
four football markets served by a live formula predictor rather than a trained model:

- `football.first_half_winner`
- `football.second_half_winner`
- `football.first_half_goals`
- `football.first_half_both_teams_to_score`

No new feature was built. No new calculator was built. This milestone is entirely a
`FeatureMarketMapping` wiring change plus the supporting per-market `is_required`/weight mechanism
needed to make that wiring safe.

## 2. Why this scope, and what changed from the initial assumption

A prior report (Milestone 5/6) named a 5th heuristic market, `football.match_result`. Investigation
before writing any code found it **deprecated and absent from the `MARKETS` tuple entirely** —
`scripts/retire_legacy_match_result_market.py` had already retired it in `dev.db`, and the market
seeder only ever maps features to markets present in `MARKETS`. There is no live code path today
that could wire a feature to it. Scope was narrowed to the 4 markets genuinely in-tuple and
live-serving.

## 3. Files changed

| File | Change |
|---|---|
| `modules/predictions/football/market_seeding.py` | New `STRUCTURED_INTEL_OPTIONAL_WEIGHTS` constant; `_seed_market` now reads a per-market `optional_features` spec key to compute `is_required` (instead of the previous global-only check against `_NEW_STAT_DIFFERENTIAL_FEATURES`), and merges weight lookup against the new dict; the four heuristic markets' `required_features` tuples now include both feature sets, each with `optional_features=(*_LINEUP_CONTINUITY_FEATURES, *_TRANSFER_ACTIVITY_FEATURES)` |
| `tests/unit/modules/predictions/test_football_market_seeding.py` | 3 new tests |
| `tests/unit/modules/predictions/test_weighted_scoring_predictors.py` | 1 new test |
| `docs/milestone8_verification_report.md` | This report |

No domain entities, database schema, migrations, repositories, or reconciliation-layer code
changed — this milestone is confined to the market-seeding/mapping layer.

## 4. Database changes

**None.** Reuses the exact `FeatureDefinition` and `FeatureMarketMapping` rows Milestones 6/7
already created — this milestone only changes what `is_required`/`weight` values get written for
four additional (market, feature) mapping pairs.

## 5. Feature Registry changes

**None.** Both feature definitions remain exactly as Milestones 6/7 left them —
`leakage_classification=PRE_MATCH_SAFE`, status ACTIVE, 24h TTL. This milestone doesn't touch
`FeatureRegistrationService` or either calculator's `ensure_registered()`.

## 6. Feature Store changes

**None.** No new writes, no new read path. `feature_values_offline` still has 0 rows for either
feature — confirmed live (§9).

## 7. Market mappings (verified against dev.db)

A design constraint required real care here: the existing `_seed_market` loop computed
`is_required` and `weight` from a single **global** check per feature key, applied identically
across every market in `MARKETS`. Simply adding lineup-continuity/transfer-activity to a shared
"optional" exclusion set would have silently downgraded them from required to optional on the 14
*trained* markets too — a real regression, since a training dataset should demand the pre-match
feature exist, exactly the completeness guarantee Milestones 6/7 built. Fixed by adding a
per-market `optional_features` spec key, defaulting to empty (no behavior change) everywhere except
the four markets this milestone touches.

Verified live against `dev.db` after re-running `scripts/seed_football_markets.py`:

```
Heuristic markets (16 mappings, 4 markets × 4 features):
  first_half_winner / second_half_winner / first_half_goals / first_half_both_teams_to_score
  → home/away_lineup_continuity: is_required=0, weight=0.1
  → home/away_transfer_activity: is_required=0, weight=0.05

Trained-market sanity check (football.match_winner, representative of all 14):
  → home/away_lineup_continuity:  is_required=1, weight=1.0  (unchanged)
  → home/away_transfer_activity:  is_required=1, weight=1.0  (unchanged)
```

`is_required=False` is not optional-in-name-only here — it's load-bearing. `resolve_feature_snapshot`
(`feature_market_mapping_service.py`) raises `MissingRequiredFeatureError` for any absent
**required** mapping; every fixture in `dev.db` today has zero non-null values for either feature
(§9), so marking these `is_required=True` on the four live-serving markets would have broken every
prediction generation attempt on all four immediately upon this milestone's own seed run.

## 8. Provenance behavior

Unchanged from Milestones 6/7 — both features are only ever written from a lineup/transfer record
whose own provenance is `VERIFIED_PRE_MATCH`. This milestone adds no new provenance logic; it only
changes which markets are permitted to *consume* an already-verified value once one exists.

## 9. Leakage analysis

| Risk | Mitigation |
|---|---|
| `is_required=True` on a live-serving market with zero non-null values anywhere → immediate `MissingRequiredFeatureError` on every prediction | Confirmed and avoided: `is_required=False` on all 4 markets, verified live |
| A market-specific opt-out silently applying to the wrong markets (the 14 trained ones) | Per-market `optional_features` key, not a global exclusion set; verified live that `football.match_winner` (representative trained market) still shows `is_required=1` |
| `transfer_activity`'s unbounded raw count saturating the formula predictor's sigmoid (the documented 2026-08-06 incident class) | Weight sized conservatively (0.05, matching `form_shots_total_diff_last5`'s comparable sizing) rather than left at the 1.0 default |
| An absent optional feature silently contributing a nonzero value to `raw_score` | Directly tested against the real predictor class (`test_logistic_predictor_ignores_a_mapped_weight_for_a_feature_absent_from_features`) — confirms byte-identical `raw_score`/`probability` whether the mapping exists with no data or doesn't exist at all |
| Fabricating a differential feature to "fix" lineup_continuity's unsigned-value limitation, adding new unverified logic under this milestone's scope | Not attempted — documented as a known limitation instead (§ Known limitations below); this milestone wires the already-verified features as-is, it does not invent a new one |
| This being genuinely live-serving (unlike M6/M7's inert-until-retrain posture) | Explicitly the point of §10/§11 below — called out, not hidden |

## 10. Tests added

`tests/unit/modules/predictions/test_football_market_seeding.py`:

- `test_seed_marks_structured_intel_features_optional_on_heuristic_markets` — confirms
  `is_required=False` for both feature sets on all 4 heuristic markets
- `test_seed_keeps_structured_intel_features_required_on_trained_markets` — confirms the same two
  feature sets stay `is_required=True` on all 14 trained markets (the regression this milestone's
  design most needed to guard against)
- `test_seed_applies_conservative_weights_to_structured_intel_features_on_heuristic_markets` —
  confirms both weights are `< 1.0` and match `STRUCTURED_INTEL_OPTIONAL_WEIGHTS` exactly

`tests/unit/modules/predictions/test_weighted_scoring_predictors.py`:

- `test_logistic_predictor_ignores_a_mapped_weight_for_a_feature_absent_from_features` — proves,
  against the actual `WeightedLogisticPredictor` class (not a stub), that a feature present in
  `mapping_weights` but absent from `features` contributes exactly nothing — byte-identical
  `raw_score`/`probability` to a prediction where the mapping doesn't exist at all.

## 11. Full test results

- `tests/unit/modules/predictions/test_football_market_seeding.py`: 12 passed (3 new).
- `tests/unit/modules/predictions/test_weighted_scoring_predictors.py`: passed (1 new).
- Full backend suite (`pytest -q`, run from `backend/`): **2024 passed, 58 skipped**, 0 failed,
  815.22s.

## 12. Regression comparison against M7

| | M7 baseline | M8 result | Delta |
|---|---|---|---|
| Passed | 2020 | 2024 | +4 (exactly the new tests added: 3 + 1) |
| Skipped | 58 | 58 | 0 |
| Failed | 0 | 0 | 0 |

No regressions.

## 13. Known limitations

- **`lineup_continuity` is fed to these formula predictors as an unsigned, always-non-negative
  ratio, not a signed differential** — unlike every other feature already safely wired into
  `weighted_scoring.py`'s predictors (`form_*_diff_last5`, the expected-goals features), which are
  all home-minus-away or otherwise signed/centered. Feeding it directly means a small constant
  positive nudge proportional to `(home + away continuity) × 0.1`, not a genuine "which side is
  more continuous" signal. This is a feature-engineering simplification, documented rather than
  solved here, to keep this milestone's scope to "wire the already-verified Milestone 6/7 features
  safely" rather than "invent a new differential feature" (which would itself need its own
  registration, leakage classification, and dedicated tests — a separate, larger milestone).
- **Weights (0.1 / 0.05) are configured defaults, not fitted values** — no real outcome history
  exists yet for these four markets to calibrate against, the same "honest v1" posture already
  documented for `NEW_STAT_FEATURE_WEIGHTS` and `TRANSFER_ACTIVITY_WINDOW_DAYS`.
- **The 4 heuristic markets' underlying formula predictors remain unretrained/uncalibrated
  generally** — this milestone does not change or improve `WeightedOrdinalPredictor`/
  `WeightedLinearPredictor`/`WeightedLogisticPredictor` themselves, only what feature set they may
  optionally draw from.

## 14. Remaining blockers

None specific to this milestone. The wiring is fully implemented, verified safe against the actual
predictor code (not just mocked), and tested. What remains blocked is unchanged from Milestones
5–7's own findings: no fixture in `dev.db` has ever produced a `VERIFIED_PRE_MATCH` lineup or
transfer record, so this milestone's real effect on a live prediction has never been, and cannot
yet be, observed.

## 15. Production impact

**None today, but genuinely different in kind from Milestones 6/7 — this is the key finding of this
milestone, not a footnote.** Milestones 6/7's `required_features` changes on the 14 trained markets
are inert until a *human* retrains and promotes a new Champion — a controlled, human-gated trigger.
This milestone's change is inert only until *data* — the moment the
`sync-upcoming-structured-intelligence-football-epl` Celery Beat task genuinely produces a
`VERIFIED_PRE_MATCH` lineup or transfer record for a fixture whose kickoff maps to one of these four
markets, the very next prediction request for that fixture on that market will silently start
factoring it in, live, with no separate rollout gate or human review step in between. This is by
design (optional features are meant to activate the moment real data exists — that's the entire
point of "fine-tune when available"), but it is a materially different production-impact profile
from every milestone since Milestone 4, and is called out explicitly here so a future operator
knows to expect it rather than being surprised by it.

Verified live against `dev.db` that nothing has changed *yet*:

```
feature_values_offline rows for lineup_continuity/transfer_activity (either feature): 0
```

Zero fixtures anywhere in the current dataset have a non-null value for either feature — the four
markets' live predictions are byte-identical to before this milestone, confirmed directly against
`WeightedLogisticPredictor` (§10's new test), not merely inferred.

## 16. Rollback procedure

Purely additive at the database level — no migration, no schema change, no existing mapping's
`is_required`/`weight` was modified (only 16 new mapping rows were created). To roll back:

1. Revert the diff (`market_seeding.py` and the two test files).
2. Optionally clean up the 16 mapping rows created by re-running the seeder — harmless to leave in
   place (an optional mapping with no consumer while `is_required=False` and no data exists is
   inert), but if desired:
   ```sql
   DELETE FROM feature_market_mappings
   WHERE market_id IN (
     SELECT id FROM prediction_markets WHERE market_key IN (
       'football.first_half_winner', 'football.second_half_winner',
       'football.first_half_goals', 'football.first_half_both_teams_to_score'
     )
   )
   AND feature_key IN (
     'football.fixture.home_lineup_continuity', 'football.fixture.away_lineup_continuity',
     'football.fixture.home_transfer_activity', 'football.fixture.away_transfer_activity'
   );
   ```
3. No Celery Beat schedule, admin endpoint, API contract, or trained model was touched — rollback
   has no operational surface beyond the code diff and the optional SQL statement above.

## Acceptance checklist

- [x] Scope narrowed correctly after investigation — `football.match_result` confirmed deprecated
      and out of scope, not silently included.
- [x] `is_required=False` confirmed safe and necessary — verified against `resolve_feature_snapshot`
      and live `dev.db` data (0 non-null values anywhere).
- [x] The 14 trained markets' existing `is_required=True` wiring confirmed unchanged — verified
      live and by dedicated test, the real regression risk this milestone's design guarded against.
- [x] Weight sizing follows the established conservative-weight precedent, explicitly avoiding the
      documented 2026-08-06 sigmoid-saturation failure mode.
- [x] "Absent optional feature contributes zero to raw_score" proven against the real predictor
      class, not assumed or mocked.
- [x] No fabricated differential feature invented to solve lineup_continuity's unsigned-value
      limitation — documented as an honest known limitation instead.
- [x] No database migration, no schema change.
- [x] 4 new tests; full backend suite green with no regressions against the M7 baseline (2024
      passed vs. 2020, +4 exactly, 58 skipped unchanged, 0 failed).
- [x] No training, retraining, or model promotion triggered by this milestone.
- [x] The genuinely-live (not inert-until-retrain) nature of this change explicitly documented as
      production impact, not glossed over.
- [x] M4–M7 documentation and existing implementation read, plus a targeted research investigation
      into the live-serving path, before any code was written; an implementation plan was presented
      to the user before implementation began.

## Stop condition

Per the standing process and the explicit instruction governing this milestone chain, this report
is the stop point. **Do not automatically begin Milestone 9** — wait for explicit approval before
proceeding.
