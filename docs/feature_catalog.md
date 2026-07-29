# TitanIQ — Feature Intelligence Platform / Feature Catalog

Status: **Platform implemented in Milestone 4** (`backend/modules/features/`) — registration
workflow, lineage validation, offline + online store all live and tested. Catalog now has real
entries: single-record calculators (Milestone 9) and one windowed team-form feature per sport
(Milestone 9), see §4. This document is the single source of truth for every feature consumed by
any model. **No model may consume an undocumented feature** — enforced today by
`FeatureStoreService.write()` refusing to persist a production value for any feature that isn't
`ACTIVE` ([FeatureRegistrationService](../backend/modules/features/application/feature_registration_service.py)),
and will additionally be enforced by a CI check diffing model training configs against
registered `feature_key`s once training pipelines exist (Milestone 6+).

## 1. Feature Record Schema

Every feature registered in `features.feature_definitions`
([database_schema.md](database_schema.md) §3) must define:

| Field | Notes |
|---|---|
| Feature ID / `feature_key` | stable, unique, e.g. `football.team.form_index_last5` |
| Name / Description | human-readable |
| Sport | `sport_code` — matches `SportCode` directly, not a cross-schema FK (docs/database_schema.md §3) |
| Category | one of §3 below — `FeatureCategory` enum, enforced at registration |
| Provider / Source | `source_provider_key` — optional loose reference to `admin.providers.key` (added in Feature Quality Intelligence, [ADR-016](decisions.md)) |
| Availability | which competitions/seasons it's populated for *(tracked via `feature_values_offline` coverage, not a definition-level field yet)* |
| Formula | exact derivation, reproducible from raw inputs — required, empty formula is rejected at registration |
| Dependencies | upstream `feature_key`s (feeds `feature_lineage`) — validated for existence and cycles before registration succeeds |
| Data type / Unit / Expected range | enforced at write time — mismatches attach `QualityFlag.TYPE_MISMATCH`/`OUT_OF_RANGE`, the value is still stored (audited, not silently dropped) |
| Update frequency / Freshness rules | free-text `update_frequency` + numeric `online_ttl_seconds` for the cache TTL |
| Validation rules | range checks, type checks — `FeatureStoreService._validate()` |
| Missing value strategy | not yet implemented — no imputation logic exists (Milestone 5, once real pipelines hit real gaps) |
| Storage location | always both — every write goes offline (durable) then online (cache); "offline only" isn't a supported mode |
| Models using it | `FeatureConsumer` registry (§8) — mechanism live, empty until Milestone 6+ models register |
| Importance score / Confidence score | not yet — populated by Outcome Learning, Milestone 11 |
| Quality / Freshness / Reliability / Completeness score | ✅ `FeatureQualityEngine.quality_snapshot()` (§8) |
| Version history | `feature_definition_versions` — append-only, one row per *superseded* version ([ADR-014](decisions.md)) |
| Owner | accountable engineer/team — required string field |

## 2. Discovery Sources

Historical match data · live match data · team/player/seasonal/competition/venue statistics ·
match events · tactical analysis · AI-extracted news · community intelligence · Knowledge Graph
relationships · outcome learning signals · mathematical/statistical derivations.

**Hard rule**: a candidate feature is only registered after a leakage check confirms it is
computable strictly from data available *before* the prediction's target event — see
[decisions.md](decisions.md) for the leakage-review process gating registration.

## 3. Feature Categories

Provider · Historical · Live · Engineered · Contextual · Tactical · Team · Player · Venue ·
Competition · Environmental · Psychological (only where measurable) · AI-Extracted · Community
Intelligence · Knowledge Graph · Learned · Meta.

## 4. Per-Sport Pipelines

Each sport owns an independent feature engineering pipeline
(`modules/sports/<sport>/application/features/`) — features are only shared across sports when
scientifically justified (e.g., a generic "days since last match" fatigue feature), and that
sharing is an explicit, documented decision, not a default.

**Milestone 9 status**: two mechanisms now populate the Feature Store for real, per
[prediction_engine.md](prediction_engine.md) §8:

- **Single-record** (`FeatureCalculatorPort` via `FeaturePipeline`,
  `backend/modules/ingestion/infrastructure/feature_calculators.py`) — computable from one
  `clean_record` dict, no repository lookup: `ImpliedProbabilityCalculator`,
  `OddsOverroundCalculator`, `HoursUntilKickoffCalculator`, `AttendanceRatioCalculator`. Each is
  parametrized (odds key, stat key) rather than one class per feature — the same handful of
  classes serve every sport's odds/schedule-shaped records.
- **Windowed** (`RollingTeamStatAverageCalculator`,
  `backend/modules/predictions/application/windowed_feature_engineering_service.py`) — a rolling
  average of one declared `TeamStatistics.stat_set` field over a team's last N matches, computed
  directly against `TeamStatisticsRepositoryPort.list_recent_by_team()` and written straight to
  the Feature Store (bypassing `FeaturePipeline`, since it needs a historical window a single
  `clean_record` can't supply). Reads each sport's *own* declared stat schema rather than an
  invented universal scoring field ([decisions.md](decisions.md) ADR-046).

| Sport | Windowed feature | Single-record features registered |
|---|---|---|
| Football | `football.team.form_shots_on_target_last5` | `football.market.implied_probability_home/away`, `football.market.overround`, `fixture.hours_until_kickoff` |
| Basketball | `basketball.team.form_points_last5` | `basketball.market.implied_probability_home/away`, `basketball.market.overround`, `fixture.hours_until_kickoff` |
| Baseball | `baseball.team.form_runs_last5` | `baseball.market.implied_probability_home/away`, `baseball.market.overround`, `fixture.hours_until_kickoff` |
| Table Tennis | `table_tennis.team.form_points_won_last5` | `table_tennis.market.implied_probability_player_a/b`, `table_tennis.market.overround`, `fixture.hours_until_kickoff` |

Representative, not exhaustive — a real, deterministic feature proving each mechanism per sport,
not the literal full advanced-metric backlog in §5. Table Tennis is modeled as `TeamStatistics`
with a roster of one (`modules.sports.table_tennis.plugin`'s `RosterRules(min_on_field=1, ...)`),
so it reuses the same windowed mechanism without a separate player-statistics port.

## 5. Candidate Advanced Metrics (reference list, not yet implemented)

Rolling/weighted/exponential moving averages · momentum indicators · form indices · power
rankings · Elo/strength ratings · possession/offensive/defensive/scoring/conversion efficiency ·
shot quality · pressure indicators · consistency indices · lineup stability · rotation
consistency · fatigue indicators · fixture congestion · travel burden · rest advantage ·
opponent strength · venue influence · trend/confidence/reliability/risk indicators · similarity
metrics · expected performance metrics.

Each of these becomes a registered feature (§1) only when implemented with a validated formula
and a leakage check — this list is a backlog, not a claim that they exist.

## 6. Feature Store Requirements

Registration ✅ · versioning ✅ · lineage ✅ · monitoring ✅ (`FeatureQualityEngine`, §8) ·
online + offline serving ✅ · caching ✅ (Redis, TTL per feature) · historical snapshots ✅
(`feature_definition_versions`, `feature_values_offline` full history) · data-quality
validation ✅ (type/range → `QualityFlag`, plus formal `FeatureValidationReport`s, §8) · drift
*detection* (statistical) — Milestone 11, table exists now · reliability tracking ✅ (§8) ·
importance tracking — Milestone 6+ (needs models) · audit history ✅ · lifecycle management ✅
(DRAFT → IN_REVIEW → ACTIVE → DEPRECATED → REMOVED, `FeatureRegistrationService`).

## 7. Milestone Mapping

Feature Store infra: ✅ Milestone 4 (`backend/modules/features/`, `backend/modules/admin/`
feature flags). Feature Quality Intelligence: ✅ extension to Milestone 4. Feature Pipeline
*architecture*: ✅ Milestone 5 (`backend/modules/ingestion/application/feature_pipeline.py`) —
zero calculators, per the constitution's explicit scope for that milestone. First real
single-record calculators (§4) and first real windowed feature per sport: ✅ Milestone 9, backing
the Prediction Intelligence Platform's registered markets ([prediction_markets.md](prediction_markets.md)
§5). Importance/confidence-contribution scoring per feature is now populated per-market via
`FeatureMarketMapping.importance`/`confidence_contribution` ([prediction_markets.md](prediction_markets.md)
§2) rather than a single Outcome-Learning-derived global score — still Milestone 11 for that.
Statistical drift *detection* wired to Outcome Learning: Milestone 11.

## 8. Feature Quality Intelligence

`FeatureQualityEngine` (`backend/modules/features/application/feature_quality_engine.py`)
computes, on demand from append-only `FeatureValue` history, everything a dashboard or a human
reviewing a feature would want to know:

- **Scores** (0-100, `None` when there's no data — never a fabricated default): Quality
  (composite: 35% reliability + 35% freshness + 30% completeness, tunable), Freshness (1.0
  within the feature's `online_ttl_seconds`, decays linearly to 0 by 5× that), Reliability
  (fraction of recent writes with no quality-flag issues), Completeness (coverage % against a
  caller-supplied expected-entity-count, or a `1 - missing_pct` proxy when none is supplied).
- **Data-quality percentages**: Missing Value %, Outlier % (`QualityFlag.OUT_OF_RANGE`),
  Invalid % (`QualityFlag.TYPE_MISMATCH`), Duplicate % (same entity + timestamp written more
  than once), Coverage %. **Null % currently equals Missing Value %** — no explicit null
  representation exists in `FeatureValue.value` yet ([ADR-017](decisions.md)).
- **Validation**: every `run_validation()` call persists a `FeatureValidationReport`
  (PASSED/WARNING/FAILED + a list of specific issues) — "Last Validation" is its
  `validated_at`, "Validation History" is the list of all of them for a feature.
- **Provider Source / Provider Reliability**: `source_provider_key` on the definition, resolved
  to a live score via `ProviderReliabilityPort` — a cross-module port to `modules/admin`'s
  Health Intelligence, not a duplicated calculation ([ADR-016](decisions.md)).
- **Computation Cost / Average Computation Time / Memory Footprint**: from
  `FeatureComputationLog`, recorded by whatever computes the feature (the future ingestion
  pipeline calls `record_computation()`).
- **Storage Size**: a JSON-size estimate over the value history, not a live Postgres query —
  no live Postgres exists in this environment yet ([ADR-018](decisions.md)).
- **Consumer Models / Usage Frequency**: `FeatureConsumer` registration and daily-bucketed
  `FeatureUsageRecord` reads — both mechanisms are real and tested; both are empty of real data
  until Milestone 6+ models exist to register and read features.
- **Deprecation Warning**: advisory string when a feature is DEPRECATED, or when its latest
  validation's quality score falls below an advisory threshold (50, tunable).

**Dashboard API** (all under `/api/v1/admin/features/{feature_key}/`): `quality`, `validate`
(POST) / `validations` / `validations/latest`, `usage` (POST/GET) / `consumers` (POST/GET),
`computation` (POST) / `statistics`, `health`.
