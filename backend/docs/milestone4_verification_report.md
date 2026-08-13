# Milestone 4 Verification Report — Data & Feature Foundation Hardening

**Status:** Complete. Per Milestone 4's own closing instruction, this is a STOP point — no
training, retraining, model promotion, sport expansion, or activation of news/community/structured
features has occurred. Waiting for explicit approval before Milestone 5.

**Scope discipline maintained throughout:** every change below is additive (new columns default to
honest "unknown"/"unverified" states; no existing column removed, renamed, or reinterpreted), no
`model.fit()` was triggered outside the pre-existing offline training path, no Champion was
promoted, no sport was expanded, and no news/community/structured-injury feature was wired into
live prediction serving.

---

## 1. Changes implemented

| # | Item | Status |
|---|---|---|
| 1 | Provider-reference join/UUID-format hardening | Done — see §5 |
| 2 | Point-in-time Feature Store retrieval | Done — see §7 |
| 3 | Temporal validity timestamp semantics | Done — see §6 |
| 4 | Injury `reported_at` leakage-risk classification | Done — see §8 |
| 5 | Champion model provenance trace | Done — see §9 |
| 6 | Model/market status honesty | Done — see §10 |
| 7 | `ModelDefinition.feature_versions` population bug | Done — see §11 |
| 8 | Feature Registry leakage classification | Done — see §12 |
| 9 | News temporal foundation (prepare, not activate) | Done — see §13 |
| 10 | Structured-intelligence foundation (prepare, not activate) | Done — see §13 |
| 11 | Point-in-time leakage-prevention tests (A–G) | Done — see §7 |
| 12 | Data quality constraints | Done — see §14 |
| 13 | FK indexing (8 named columns) | Done — see §14 |
| 14 | Prohibition list (no training/promotion/expansion) | Honored throughout |

## 2. Files changed

**New:**
- `alembic/versions/0038_milestone4_provenance_foundation.py`
- `alembic/versions/0039_milestone4_data_quality_constraints.py`
- `scripts/normalize_provider_ref_index_entity_id.py`
- `scripts/trace_football_champion_provenance.py`
- `docs/milestone2_market_feature_news_mapping.md` (Milestone 2 deliverable)
- `docs/milestone3_historical_data_audit.md` (Milestone 3 deliverable)
- `docs/milestone4_verification_report.md` (this file)

**Modified (backend):**
- `modules/ingestion/infrastructure/persistence/mappers.py` — `_canonical_entity_id`
- `modules/ingestion/infrastructure/persistence/repositories.py` — `SqlAlchemyProviderRefIndexRepository.get()`
- `modules/features/infrastructure/persistence/mappers.py` — `_canonical_entity_id`, leakage-classification carry-through
- `modules/features/infrastructure/persistence/repositories.py` — `SqlAlchemyFeatureValueRepository.get_as_of()`
- `modules/features/infrastructure/persistence/models.py` — `FeatureDefinitionModel.leakage_classification`
- `modules/features/ports/repositories.py` — `FeatureValueRepositoryPort.get_as_of`
- `modules/features/application/feature_store_service.py` — `FeatureStoreService.read_as_of()`
- `modules/features/domain/entities.py` — `FeatureDefinition.leakage_classification`, `is_market_safe()`
- `modules/predictions/application/feature_market_mapping_service.py` — `FeatureLeakageRiskError`, enforcement in `map_feature()`
- `modules/predictions/application/model_selection_service.py` — `feature_versions` population, `TIME_SERIES_SPLIT` default
- `modules/predictions/application/training_pipeline_service.py` — fold-based split fix in `train()`
- `modules/predictions/domain/entities.py` — `ModelDefinition.provenance_status`, `is_genuinely_trained()`
- `modules/predictions/infrastructure/persistence/models.py` — `ModelDefinitionModel.provenance_status`, `PredictionAuditModel` indexes
- `modules/predictions/infrastructure/persistence/mappers.py` — `provenance_status` carry-through
- `modules/sports/domain/entities.py` — `availability_classification`/`information_available_at` on Injury/Suspension/Transfer/Lineup
- `modules/sports/infrastructure/persistence/models.py` — same fields + 6 FK indexes
- `modules/sports/infrastructure/persistence/mappers.py` — carry-through for the 4 entities
- `modules/sports/infrastructure/providers/api_sports_adapter.py` — `reported_at` finding documented
- `modules/intelligence/infrastructure/persistence/models.py` — `NewsArticleModel.information_available_at` (groundwork only)
- `apps/api/composition.py` — `feature_definitions` wired into `AutomaticModelSelectionService`
- `apps/api/routers/market_router.py` — `training_status` in market serialization
- `apps/api/routers/ml_platform_router.py` — `is_genuinely_trained` in model serialization

**Modified (tests):**
- `tests/unit/modules/ingestion/test_entity_reconciliation_service.py` — `TestProviderRefIndexCanonicalEntityId` (4 tests)
- `tests/unit/modules/features/test_feature_store_service.py` — `TestPointInTimeLeakagePrevention` (7 tests, A–G)
- `tests/unit/modules/features/test_repositories.py` — 2 `get_as_of` tests against the real SQLAlchemy repo
- `tests/unit/modules/features/conftest.py` — `get_as_of` added to the in-memory test double
- `tests/unit/modules/predictions/test_model_selection_service.py` — `SplitStrategy.TRAIN_TEST` made explicit where the test depends on it
- `tests/unit/apps/test_api_markets.py` — 3 `training_status` tests
- `tests/unit/apps/test_api_ml_platform.py` — 2 `is_genuinely_trained` tests

## 3. Migrations

- **0038** — additive: 8 FK indexes; `availability_classification`+`information_available_at` on
  `injuries`/`suspensions`/`transfers`/`lineups` (default `UNKNOWN_AVAILABILITY_TIME`);
  `provenance_status` on `models` (default `PROVENANCE_UNVERIFIED`); `leakage_classification` on
  `feature_definitions` (default `UNKNOWN_PROVENANCE`); `information_available_at` on
  `news_articles` (groundwork, unpopulated). Full `downgrade()` provided.
- **0039** — additive: 2 CHECK constraints on `fixtures.home_score`/`away_score` (Postgres only —
  SQLite can't add a CHECK constraint to an existing table without a full rebuild; the migration
  detects the dialect and no-ops there rather than failing).

Applied directly to `dev.db` via a one-off Python script (dev.db is not Alembic-managed locally,
per this project's established convention — `alembic upgrade head` fails against it with "unknown
database sports"). Output confirmed every index/column created with no errors. The CHECK
constraints in 0039 were verified against dev.db as unnecessary today (zero negative-score rows
exist) and are Postgres-only by design, so nothing further was needed there.

## 4. Provider-reference indexes

8 new indexes: `fixtures.home_team_id`/`away_team_id`/`venue_id`, `teams.venue_id`,
`match_events.team_id`/`player_id`, `prediction_audits.market_id`/`model_id`. Verified none
duplicated an existing index under another name before creation.

## 5. Provider-reference join/UUID-format fix

**Investigation.** Milestone 3 flagged a byte-level format mismatch: real entity PK columns
(`fixtures.id`, `teams.id`, etc.) store SQLite `Uuid` values as 32-char hex-no-hyphen, while
`provider_ref_index.entity_id`/`feature_values_offline.entity_id` are plain `String` columns whose
values came from whatever `str()` happened to produce at each call site.

**First hypothesis (superseded).** Normalize `entity_id` to hex, matching the PK columns' raw
storage format. Reverted after the test suite caught a real regression: `_notify_fixture_status_change`'s
"favorite team" alert lookup compares a `_resolve()`-returned team id against `WatchlistEntry.entity_ref`
— which every real call site populates via plain `str(some_id.value)`, i.e. the **hyphenated**
canonical `uuid.UUID` string form. Hex-normalizing `entity_id` broke this real, working path.

**Corrected fix.** `_canonical_entity_id()` (both `modules/ingestion` and `modules/features`
mappers) normalizes to `str(uuid.UUID(value))` — hyphenated — with a tolerant fallback for
non-UUID values (test fixtures using mnemonic ids like `"team-1"`). Applied at every mapper
read/write choke point.

**Read-path gap found and fixed during this session's own verification.** `SqlAlchemyProviderRefIndexRepository.get()`
— the method `EntityReconciliationService._resolve()` actually calls in production — returned
`model.entity_id` raw, bypassing `_canonical_entity_id` entirely; only `upsert()`'s return value
went through the mapper. A legacy hex-stored row would have silently failed the same
favorite-team-alert string comparison the original fix was meant to close. Fixed by routing `get()`
through `mappers.ref_index_to_domain()`.

**Existing dev.db data.** 7,529 `provider_ref_index` rows checked; 3 were stored in raw hex
(pre-dating the fix, all `football_data_org` team refs). Backfilled to canonical hyphenated form
via `scripts/normalize_provider_ref_index_entity_id.py`, which documents the transformation and is
idempotent (a second run reports zero rows needing normalization — confirmed).

**Tests.** `TestProviderRefIndexCanonicalEntityId` (4 tests, against a real SQLite session, not a
fake): team/player/fixture provider-ref → canonical entity → repository lookup round-trips
correctly, and a row still stored in raw hex resolves identically to a canonical one (proving the
read path doesn't depend on every row having already been migrated).

## 6. Temporal validity timestamp semantics

Two independent temporal concepts exist in the schema today, deliberately not merged into one:

- **Feature Store `as_of`** (`feature_values_offline.as_of`, `NOT NULL`) — when a feature's value
  became true, not when it was written to the store. The sole dimension `get_as_of()`/`read_as_of()`
  filter on: `WHERE as_of <= cutoff ORDER BY as_of DESC LIMIT 1`. Insertion order is irrelevant —
  proven by leakage-prevention test G (§7). Because it's `NOT NULL`, "unknown timestamp" cannot
  literally occur in this table; a value either has a real `as_of` or doesn't exist yet.
- **Structured-intelligence `availability_classification`/`information_available_at`**
  (`injuries`/`suspensions`/`transfers`/`lineups`) — a 3-state concept
  (`VERIFIED_PRE_MATCH`/`VERIFIED_POST_MATCH`/`UNKNOWN_AVAILABILITY_TIME`, named for injuries
  specifically; the same shape as the general `KNOWN_BEFORE_EVENT`/`UNKNOWN`/`KNOWN_AFTER_EVENT`
  taxonomy Milestone 4's own spec named) answering "was this fact knowable before kickoff," which
  the source data often cannot answer today (§8) — hence the honest default of "unknown," never
  auto-classified as pre-match.

These are deliberately separate: Feature Store `as_of` is a hard cutoff a query can filter on
directly; structured-intelligence availability classification is a confidence label about whether
that cutoff is even knowable for a given record, pending a real verification pass this milestone
does not attempt (per its own "never fabricate" rule).

## 7. Feature Store point-in-time retrieval

`FeatureValueRepositoryPort.get_as_of()` (additive to the port) backed by
`SqlAlchemyFeatureValueRepository.get_as_of()`; `FeatureStoreService.read_as_of()` is the service
entry point, deliberately bypassing the Redis online cache (no as-of dimension there) and reading
`offline.get_as_of()` directly.

**Leakage-prevention tests A–G** (`TestPointInTimeLeakagePrevention` in
`test_feature_store_service.py`, run against `service.read_as_of()` — the real served path, not a
raw repository call):

| Scenario | Result |
|---|---|
| A — pre-kickoff value included | Pass |
| B — post-kickoff value excluded | Pass |
| C — unknown-timestamp excluded by default | N/A to the Feature Store (schema enforces `as_of NOT NULL`) — real analogue is §8/§6's structured-intelligence classification, documented rather than silently skipped |
| D — post-match stat excluded at a pre-match cutoff | Pass (same mechanism as B) |
| E — future-fixture stats absent entirely | Pass |
| F — versioned historical retrieval returns the value true at that cutoff, not the latest | Pass |
| G — late-ingested-but-early-`as_of` value still included (insertion order irrelevant) | Pass |

Two additional tests (`test_feature_value_get_as_of_returns_value_true_at_cutoff_not_the_latest`,
`test_feature_value_get_as_of_returns_none_before_any_value_existed`) exercise the real
SQLAlchemy-backed repository directly, not the in-memory test double — verifying the SQL itself,
not just a hand-written fake that could silently diverge from it (the exact class of bug caught in
§5).

## 8. Injury `reported_at` leakage-risk finding

Read `ApiFootballAdapter.fetch_injuries` line-by-line: `reported_at` is populated from the
API-Football `/injuries` response's `fixture.date` field — the **kickoff time of the referenced
fixture**, not a genuine report/publication timestamp. That endpoint reports no such timestamp at
all. This is a real, adapter-level finding (documented in the adapter's own docstring), not a
backfill-script artifact as Milestone 3's audit speculated.

**Consequence:** an injury's `reported_at` cannot be trusted to answer "was this known before
kickoff" — using it directly would systematically overstate pre-match knowability. This is exactly
why `availability_classification` defaults to `UNKNOWN_AVAILABILITY_TIME` rather than being
derived from `reported_at`.

**Existing data confirmed honest.** All 30 `injuries`, 308 `transfers`, 4 `lineups` (0
`suspensions` — table is empty, no active reconciliation path) rows default to
`UNKNOWN_AVAILABILITY_TIME`. No row was auto-classified as pre-match.

## 9. Existing football Champion model provenance

`scripts/trace_football_champion_provenance.py` (read-only report, never writes
`provenance_status`) traces every football CHAMPION model. Run against dev.db:

- **19 football Champions total.**
- **14 genuinely trained** (`catboost_gbm`/`lightgbm_gbm`/`logistic_regression`/`svm`/`elastic_net`/`gaussian_nb`,
  `dataset_version=1`, real `trained_at`, `artifact_ref` populated).
- **5 heuristic placeholders** (`heuristic_logistic_v1`, `dataset_version=None`, `trained_at=None`,
  no `artifact_ref`) — see §10.
- **None of the 19** carry `training_dataset_ref`/`training_run_ref` (they predate
  `AutomaticModelSelectionService` populating those fields), so none are `provenance_traceable` by
  the script's own strict definition — every one correctly remains `PROVENANCE_UNVERIFIED`. This
  is a known, documented gap the script flags explicitly, not a defect this migration fixes; no
  row was reclassified `PROVENANCE_VERIFIED` because doing so would require a training-run
  artifact that doesn't exist to point to.

## 10. Model/market status honesty (Rule 13)

**Real gap found:** 5 football markets (`first_half_both_teams_to_score`, `first_half_goals`,
`first_half_winner`, `match_result`, `second_half_winner`) carry a placeholder-heuristic Champion
registered solely to unblock `PredictionContextBuilder` (which only raises `NoChampionModelError`
when a market has *no* Champion at all) — never a genuinely fit-and-validated model. Before this
fix, they reported the same `status: "champion"`/market `status: "production"` as the 14 real
trained markets, with no field distinguishing them.

**Fix.** `ModelDefinition.is_genuinely_trained()` — `artifact_ref is not None` — reuses an
already-load-bearing signal (`PredictionEngine._resolve_predictor` already requires it before
using a trained model over the generic formula fallback) rather than inventing a new field or
misusing `deployment_mode` (which already carries an unrelated, real meaning — rollout stage:
`shadow`/`canary`/`live` — confirmed by reading the domain entity before reusing it, avoiding the
collision the original Milestone 2 proposal to repurpose `deployment_mode` would have caused).

Surfaced two places:
- `GET /api/v1/markets` / `GET /api/v1/markets/{key}` — new `training_status` field:
  `NO_CHAMPION` / `HEURISTIC_PLACEHOLDER` / `TRAINED`.
- `GET /api/v1/admin/ml/models/{market_key}` — new `is_genuinely_trained` boolean per model row.

**Deliberately not changed:** prediction *generation* for these 5 markets — they continue serving
the existing heuristic fallback exactly as before. Milestone 4 prohibits sport/market expansion and
new training; blocking generation entirely would be a product regression (removing existing
functionality) that wasn't authorized. Status honesty here means the API tells the truth about
what backs a prediction, not that serving stops.

**Not done (explicitly out of scope for Milestone 4):** frontend surfacing of `training_status`/
`is_genuinely_trained` — AI Picks currently renders a heuristic-derived prediction identically to a
trained one. The data is now available via API; a future milestone can design the UI treatment.

## 11. `ModelDefinition.feature_versions` population bug

`AutomaticModelSelectionService.select_and_register_challenger()` never passed `feature_versions`
to `model_registry.register()`, silently leaving every model's `feature_versions` at `{}` despite
the field existing since Milestone 9.1. Fixed via `_resolve_feature_versions()`, which looks up
each feature key's current `FeatureDefinition.version` through the newly-wired
`feature_definitions: FeatureDefinitionRepositoryPort` dependency (added to `composition.py`).
Applies to models registered **going forward** — the 19 existing Champions (§9) were registered
before this fix and still show `feature_versions: {}`, consistent with §9's "no fabricated
verified state" discipline (their real feature-version lineage cannot be reconstructed
retroactively).

## 12. Feature Registry leakage classification

`FeatureDefinition.leakage_classification` — `PRE_MATCH_SAFE`/`POST_MATCH_ONLY`/
`POINT_IN_TIME_REQUIRED`/`UNKNOWN_PROVENANCE` (default) — complements, does not replace, the
existing `leakage_reviewed: bool`. `is_market_safe()` returns `False` only for `POST_MATCH_ONLY`.
Enforced at `FeatureMarketMappingService.map_feature()`'s single choke point: mapping a
`POST_MATCH_ONLY` feature into any market now raises `FeatureLeakageRiskError`, checked immediately
after the existing `is_consumable()` gate. Every existing feature definition defaults to
`UNKNOWN_PROVENANCE` (not `PRE_MATCH_SAFE`) — nothing was auto-classified as safe.

## 13. News and structured-intelligence temporal foundation — prepared, not activated

**Prepared (schema/groundwork only, per Milestone 4's explicit "prepare, do not activate"
instruction):**
- `news_articles.information_available_at` (nullable, unpopulated) — deliberately **not** wired
  into the `NewsArticle` domain entity or its mapper. No news feature reaches
  `FeatureMarketMapping` or `PredictionContextBuilder` today; this column exists only so a future
  milestone has somewhere to write the timestamp when that work is authorized.
- `availability_classification`/`information_available_at` on `injuries`/`suspensions`/`transfers`/`lineups`
  — populated (defaults to unknown, §8), but **no consumer wired**: no `FeatureMarketMapping`
  references any structured-intelligence field, so nothing currently reads these classifications
  into a live prediction. `EntityReconciliationService.reconcile_injury`/`reconcile_transfer`
  already existed before this milestone and are unchanged in this respect — they persist domain
  rows, they don't feed features.

**What remains for a future milestone to activate** (explicitly deferred, not attempted here):
1. A `FeatureMarketMapping` entry making a structured-intelligence field (e.g. "starting
   goalkeeper injured") an actual model input — requires the market-specific impact-weighting
   design work Milestone 2 scoped but did not implement.
2. Populating `information_available_at` for real — requires either a genuine provider-reported
   timestamp (which §8 found doesn't exist for injuries today) or a documented, defensible
   inference rule that isn't fabrication.
3. News ingestion's own event-confidence taxonomy (`CONFIRMED`/`PROBABLE`/`UNCERTAIN`/`RUMOUR`/
   `CONTRADICTED`/`EXPIRED`) and market-specific impact weighting — both still `MISSING` per
   Milestone 2's audit, unchanged by this milestone.

## 14. Data quality constraints and FK indexes

FK indexes: see §4. Data quality constraints: see migration 0039 (§3) — 2 CHECK constraints on
`fixtures.home_score`/`away_score >= 0`, deliberately narrow (see the migration's own docstring for
why a blanket constraint pass was rejected in favor of the specific, real gap found: nothing today
validates a provider-supplied score before persisting it).

## 15. Tests added

- `tests/unit/modules/ingestion/test_entity_reconciliation_service.py::TestProviderRefIndexCanonicalEntityId` — 4 tests
- `tests/unit/modules/features/test_feature_store_service.py::TestPointInTimeLeakagePrevention` — 7 tests (A–G)
- `tests/unit/modules/features/test_repositories.py` — 2 `get_as_of` tests (real repository)
- `tests/unit/apps/test_api_markets.py` — 3 `training_status` tests
- `tests/unit/apps/test_api_ml_platform.py` — 2 `is_genuinely_trained` tests

18 new tests total.

## 16. Tests passed

- Targeted suites (ingestion/sports/features/watchlist) after the read-path fix in §5: 480 passed.
- `tests/unit/apps/test_api_markets.py` + `test_api_ml_platform.py`: 65 passed.
- `tests/unit/modules/features`: 99 passed.
- Full `tests/unit` suite: run three times during this milestone (before the §5 read-path fix,
  after it at 1959 passed/0 failed, and again after every remaining Milestone 4 change including
  the leakage-prevention tests and the data-quality-constraints migration) — final run: **1973
  passed, 0 failed**, in 826.64s. No regressions found at any point.

## 17. Remaining leakage risks (known, not fixed by this milestone)

- The 14 genuinely-trained football Champions (§9) were trained on datasets Milestone 3 found to
  be backfill-derived, predating the point-in-time infrastructure this milestone built (§7). Their
  training data's own leakage-safety cannot be independently re-verified after the fact — this is
  why none of them are `PROVENANCE_VERIFIED`, and why Milestone 4 does not attempt to retrain them
  (retraining is explicitly out of scope; a future milestone can retrain under `TIME_SERIES_SPLIT`,
  now the live default, per §11's docstring in `model_selection_service.py`).
- `feature_values_offline.entity_id`/`provider_ref_index.entity_id` remain plain `String` columns
  with mapper-layer (not database-layer) canonicalization. A future write path that bypasses the
  mapper (raw SQL, a new adapter that doesn't go through `mappers.py`) could reintroduce
  non-canonical values undetected until a lookup fails. No such path exists today — flagged as a
  structural risk, not a current bug.

## 18. Training readiness after Milestone 4

Unchanged from Milestone 3's determination: the 14 real football markets are already
`PRODUCTION_READY` (trained, serving); the 5 heuristic-placeholder markets are honestly now
reported as such via `training_status`/`is_genuinely_trained` (§10) rather than silently
misrepresented; Basketball/Baseball/Tennis remain `INSUFFICIENT_DATA`/`MISSING` respectively, per
Milestone 3's audit — nothing in Milestone 4 changed that determination, as instructed.

## What remains blocked (per Milestone 4's own closing instruction)

Explicit wait for approval before: training new models, retraining existing models, activating
news features, activating community features, activating structured injury/lineup/transfer
features into live prediction serving, expanding Basketball/Baseball/Tennis prediction models,
promoting any new Champion.

## Recommended Milestone 5 scope (for consideration, not committed)

1. Design and implement the market-specific structured-intelligence feature (§13 item 1) —
   the highest-value, most self-contained next step, since the data and classification taxonomy
   already exist.
2. Retrain the 14 existing football Champions under `TIME_SERIES_SPLIT` (now the live default) and
   compare against the current Champions via the existing `ChallengerEvaluationService` before any
   promotion — closes §17's leakage-verification gap for real, rather than leaving it as a known
   risk.
3. News ingestion event-confidence taxonomy + market-specific impact weighting (Milestone 2 §1.2b/§1.3).

---

## Acceptance checklist

- [x] Provider-reference join bug fixed at both read and write paths, with a real regression
      caught and corrected during this milestone's own verification (§5).
- [x] Point-in-time Feature Store retrieval implemented and covered by 9 real tests (§7).
- [x] Temporal validity semantics documented for both timestamp concepts the schema carries (§6).
- [x] Injury `reported_at` leakage risk traced to its adapter-level root cause, not guessed (§8).
- [x] Every existing Champion's provenance traced by a reusable, read-only script; none
      misclassified `PROVENANCE_VERIFIED` (§9).
- [x] Model/market status honesty gap found and fixed without changing serving behavior (§10).
- [x] `feature_versions` population bug fixed at its one real call site (§11).
- [x] Feature Registry leakage classification enforced at a single choke point (§12).
- [x] News/structured-intelligence groundwork laid without activation; deferred work enumerated (§13).
- [x] 8 FK indexes added, verified no duplicates (§4/§14).
- [x] Data quality constraints added narrowly, with a documented rationale for what was
      deliberately not added (§14).
- [x] 18 new tests written and passing; full suite green (§15/§16).
- [x] No training, retraining, promotion, or sport expansion occurred.
- [x] No feature/model/market was fabricated a "verified"/"safe"/"trained" status it hadn't earned.
- [x] Remaining leakage risks documented explicitly, not silently left implicit (§17).
- [x] STOP condition honored — this report ends without proceeding to Milestone 5.
