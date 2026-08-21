# POST-M24 PRODUCTION READINESS & TRAINING UNBLOCK — Deliverable 1 Verification Report

**Scope of this turn (per the master prompt's explicit execution-mode instruction):** audit the
existing outcome-resolution architecture and implement the missing first-half/second-half outcome
resolvers (Group B, 4 markets) if the existing data model supports them; run targeted tests, run
full backend regression, run TrainingPreflight against the 14 genuinely-trained football markets
(Group A); report. **No basketball/baseball/table-tennis work (Phases 8–10) was started.** No
training, retraining, calibration, promotion, Champion seeding, Kaggle integration, or provenance
change was performed.

---

## 1. Audit finding: the resolvers were missing, the data was not

Read the real source before writing anything:

- `modules/predictions/application/outcome_resolution_service.py` had three resolver-shape
  registries (binary, three-way, grid) but **no entries at all** for
  `football.first_half_winner`, `football.second_half_winner`, `football.first_half_goals`,
  `football.first_half_both_teams_to_score`.
- `modules/predictions/domain/market_outcome_registry.py`'s catalog had all 4 markets specified
  (name, outcome type, allowed values) but every one had `resolver_key=None` — the catalog was
  already honest that no resolver existed for them.
- Confirmed via direct `dev.db` query that all 4 already exist as `production`-status markets
  (seeded in an earlier milestone), so this was purely an application-layer gap, exactly as the
  master prompt framed Group B — **"NOT a dataset shortage… application-layer functionality
  missing from the outcome pipeline."**
- Read every football provider adapter (`api_sports_adapter.py`'s `ApiFootballAdapter`,
  `football_data_org_adapter.py`) end to end: neither ever parses a half-time score. Only
  `fullTime`/`goals` (final score) is extracted. `Fixture.period_scores` (the JSON column that
  already carries basketball's quarter scores and baseball's inning scores) is `None` for every
  football fixture — its own field comment already said so before this turn.

Conclusion: the resolver *logic* was buildable today from data the domain model already supports
(`period_scores`'s existing `{"kind", "home", "away"}` shape just needed a new `"half"` kind); the
resolver *executing against real data* is blocked on a separate, not-yet-authorized ingestion gap
(no football adapter fetches half-time scores). This distinction is threaded through every piece of
code and every test written this turn — nothing claims more than what is actually true.

## 2. What was built

**`modules/predictions/application/outcome_resolution_service.py`**
- `MatchResult` extended with optional `home_score_ht` / `away_score_ht` fields (default `None` —
  every existing call site is unaffected).
- Four new resolver functions, fail-closed on missing or impossible data (never fabricates, never
  guesses):
  - `_first_half_both_teams_to_score`, `_first_half_goals_over_under_0_5` — binary resolvers,
    registered in `MARKET_OUTCOME_RESOLVERS`.
  - `_first_half_winner`, `_second_half_winner` — three-way resolvers, registered in
    `THREE_WAY_MARKET_RESOLVERS`. `_second_half_winner` derives second-half goals as
    `full_time − half_time` per side and returns `None` if either side would go negative
    (an impossible/corrupt data case).
- **Bug fix, self-identified while designing these resolvers:** `resolve_for_fixture`'s
  three-way/grid branch had no `None`-check before building and recording a `PredictionOutcome` —
  a real gap that would have silently recorded a fabricated outcome the first time any three-way or
  grid resolver returned `None`. Added `if actual_label is None: continue`, mirroring the pattern
  the binary branch already used.
- `resolve_for_fixture` signature extended with keyword-only `home_score_ht=None`,
  `away_score_ht=None`, passed through to `MatchResult`. Backward-compatible: no existing caller is
  affected unless it explicitly opts in.

**`modules/ingestion/application/entity_reconciliation_service.py`**
- New `_extract_half_time_scores(fixture)` helper reads `fixture.period_scores` for
  `kind == "half"` and returns `(home[0], away[0])`, or `(None, None)` for every fixture in the
  codebase today — its own docstring says so honestly.
- `_resolve_prediction_outcomes` (the real production call site, fired whenever a fixture reaches
  `COMPLETED` with a score) now extracts and threads half-time scores through to
  `resolve_for_fixture`.

**`modules/predictions/domain/market_outcome_registry.py`**
- Set `resolver_key` on all 4 Group B catalog entries. Module docstring and inline comments updated
  to state precisely what changed: resolution *logic* exists; resolution *data* does not yet.

**`modules/predictions/application/outcome_label_mapper.py`**
- Added the two binary Group B markets' real-label pairs
  (`first_half_goals`→OVER/UNDER, `first_half_both_teams_to_score`→YES/NO) to
  `MARKET_OUTCOME_LABELS`, so generation and evaluation agree on one label convention — same
  pattern as every other binary market.

No provenance code, no `SyncTrigger`, no `TrainingPreflightService`, no `DatasetBuilder`, and no
football provider adapter was touched. No new Champion model, dataset, or fixture was created.

## 3. Tests

**New/updated test coverage** (`tests/unit/modules/predictions/test_outcome_resolution_service.py`):
17 direct unit tests covering the master prompt's exact Phase 4 matrix —

| Case | Expected |
|---|---|
| HT 1–0 | first_half_winner = HOME |
| HT 0–1 | first_half_winner = AWAY |
| HT 0–0 | first_half_winner = DRAW |
| HT 2–2 | first_half_winner = DRAW |
| FT 3–1, HT 1–1 | second_half_winner = HOME |
| FT 1–3, HT 1–1 | second_half_winner = AWAY |
| FT 2–2, HT 1–1 | second_half_winner = DRAW |
| FT 1–1, HT 0–0 | second_half_winner = DRAW |
| Missing HT score | all 4 resolvers return `None` (fail closed) |
| Missing FT score | all 4 resolvers return `None` (fail closed) |
| Impossible negative derived 2nd-half goals | `_second_half_winner` returns `None` (fail closed) |

Plus 4 end-to-end `resolve_for_fixture(..., home_score_ht=..., away_score_ht=...)` tests proving
real resolution happens once half-time data is supplied, including a fail-closed impossible-data
case at the service boundary.

**Stale-assertion sweep** (found and fixed proactively, before running anything, by grepping every
touched symbol across the whole suite):
- `test_football_market_seeding.py` — a test asserted `first_half_winner.resolver_key is None`;
  now asserts the real value.
- `test_market_outcome_registry.py` — `MARKETS_WITH_REAL_RESOLVER` didn't include the 4 new
  entries, which would have failed the suite's own "every other market has `resolver_key is None`"
  check.
- `test_api_prediction_analytics.py`, `test_outcome_resolution_service.py` — stale comments claiming
  "no resolver exists" for these markets, corrected for accuracy.

**Real bug found and fixed mid-verification:** `test_entity_reconciliation_service.py`'s
`_RecordingOutcomeResolver` stub didn't accept the new `home_score_ht`/`away_score_ht` keyword
arguments that `_resolve_prediction_outcomes` now always passes — confirmed via a full traceback
(`TypeError: got an unexpected keyword argument 'home_score_ht'`) before fixing it, not assumed.
Fixed by widening the stub's signature to accept and ignore them, keyword-only with `None`
defaults, preserving its existing `self.calls` tuple shape.

**Unrelated environment gap found and ruled out:** an initial full-suite run showed 18 failures in
`test_api_prediction_analytics.py`, all `ValueError: Fernet key must be 32 url-safe base64-encoded
bytes` / `pydantic ValidationError` originating from `modules/admin/infrastructure/vault.py`'s
`VaultSettings` — this shell's `TITANIQ_ENCRYPTION_KEY` environment variable was absent/invalid. It
is unrelated to this turn's code: the failure traces through `composition.py`'s
`build_provider_management_service`, nowhere near outcome resolution. Confirmed root cause by
regenerating a valid Fernet key and re-running the file in isolation (21/21 passed) before trusting
any full-suite result.

### Final results

- **Targeted files** (`test_outcome_resolution_service.py`, `test_outcome_label_mapper.py`,
  `test_market_outcome_registry.py`, `test_football_market_seeding.py`,
  `test_api_prediction_analytics.py`, `test_entity_reconciliation_service.py`): all green after the
  stub fix.
- **Full backend regression suite** (`pytest -q`, `TITANIQ_ENCRYPTION_KEY` set to a valid key):
  **2256 passed, 58 skipped, 0 failed** (31m28s). Zero regressions.

## 4. `dev.db` state change (metadata only)

`FootballMarketSeeder._seed_market` is insert-only (`MarketAlreadyRegisteredError` → `pass`) — it
does not update an already-registered market's columns. Since all 4 Group B markets were already
`production`-status rows from an earlier milestone, re-running the full seeder script would not
have picked up the new `resolver_key` values, and would additionally have minted 4 new placeholder
`CHAMPION` models for markets that don't have one yet — the master prompt reserves Champion seeding
for a separate, later authorization. Instead, applied a narrow, direct, idempotent `UPDATE
prediction_markets SET resolver_key = ... WHERE market_key = ...` for exactly the 4 rows, verified
before and after:

| market_key | resolver_key before | resolver_key after |
|---|---|---|
| football.first_half_winner | `NULL` | `football.first_half_winner` |
| football.second_half_winner | `NULL` | `football.second_half_winner` |
| football.first_half_goals | `NULL` | `football.first_half_goals` |
| football.first_half_both_teams_to_score | `NULL` | `football.first_half_both_teams_to_score` |

No Champion model, feature mapping, dataset, or fixture was created or modified. Confirmed via
read-only query: **all 4 markets have 0 `PredictionOutcome` rows** (11,194 exist across the whole
platform, none for these 4) — exactly as expected, since no adapter populates half-time scores yet.
This is stated plainly, not implied otherwise: the resolvers are real and tested; they have not yet
resolved a single real outcome in production, and cannot until a football provider adapter parses
`halfTime`/`HT` scores — an ingestion change explicitly out of scope for this turn.

## 5. TrainingPreflight — Group A (14 genuinely-trained football markets)

`scripts/run_training_preflight.py --all-trained-football`, read-only, against live `dev.db`:

**0/14 markets READY for training.**

Every one of the 14 fails the same two checks, for the same reason:

- **`training_inference_feature_parity` / `required_feature_coverage_acceptable`**: 0.0% coverage
  for `football.fixture.{home,away}_lineup_continuity`, `football.fixture.{home,away}_transfer_activity`,
  and each market's applicable news-impact feature (e.g. `news.football.{home,away}_goal_impact`,
  `_clean_sheet_impact`, `_btts_impact`). These are required at live inference but present in **zero**
  training samples — exactly the master prompt's own Group A diagnosis: blocked by gated pre-match
  intelligence features that require genuine `LIVE_SCHEDULED` provenance, which the platform is
  correctly still accumulating rather than fabricating.
- **`dataset_provenance_persisted`**: fails for all 14 by design — `DatasetRepositoryPort` is
  in-memory-only (documented in the M19 audit §13 / ADR-008), not a data problem.

Every other check passes for all 14 (market exists, feature manifest declared, 653–824 labeled
samples each — well above the 30-sample minimum, labels valid, temporal reference present,
chronological split intact, feature versions active, no leakage-classified required feature,
reproducible dataset hash). This is not a training bug to route around — it is the platform
correctly waiting for the pre-match intelligence features (lineup continuity, transfer activity,
news impact) it does not yet have enough genuine `LIVE_SCHEDULED` observations to populate, per the
master prompt's own instruction: "the correct solution is continued accumulation of genuine live
observations."

## 6. Summary

| Item | Status |
|---|---|
| Group B resolver audit | Complete — root cause confirmed via direct source read |
| 4 half-result resolvers implemented | Complete, fail-closed, backward-compatible |
| Targeted test matrix (Phase 4 spec) | Complete — 17 direct + 4 end-to-end tests, all green |
| Full backend regression | 2256 passed / 58 skipped / 0 failed |
| `dev.db` resolver_key persisted | Complete — 4-row metadata-only UPDATE, verified |
| Group B real outcomes resolved | **0** — honest, expected, blocked on missing half-time ingestion |
| Group A TrainingPreflight | **0/14 READY** — blocked on structured-intel feature coverage, as predicted |
| First legitimate training candidate | **Not yet reached** — no market is training-ready today |
| Basketball / baseball / table-tennis (Phases 8–10) | **Not started**, per explicit instruction |
| Training / retraining / calibration / promotion / Champion seeding | **None performed** |

**STOPPING HERE**, per the master prompt's explicit instruction not to proceed automatically to
basketball/baseball/table-tennis work. Awaiting direction on whether to pursue the football
half-time-score ingestion gap (the one remaining piece that would let Group B's resolvers resolve
real outcomes) or another phase.
