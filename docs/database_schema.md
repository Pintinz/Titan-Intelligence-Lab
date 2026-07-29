# TitanIQ — Database Schema

Status: Foundation design (pre-Milestone-1) — no migrations have been generated yet. This
document defines the initial schema shape; Alembic migrations become the executable source of
truth once Milestone 2 (Data Layer) begins. Every schema change must update this document in
the same PR (see [roadmap.md](roadmap.md) Definition of Done).

## 1. Conventions

- Every table: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at`, `updated_at`
  (trigger-maintained), `deleted_at` (soft delete, nullable) unless explicitly noted.
- Schema-per-bounded-context using Postgres schemas: `sports`, `features`, `predictions`,
  `knowledge_graph`, `identity`, `billing`, `content`, `analytics`, `admin` — mirrors the module
  boundaries in [architecture.md](architecture.md) §3.
- All user-scoped tables carry `owner_id UUID REFERENCES identity.users(id)` and an RLS policy
  restricting rows to `auth.uid() = owner_id` (or role-based override) — see
  [security.md](security.md) §"Row-Level Security".
- Foreign keys to provider-external identifiers are stored as `provider_ref JSONB` on the owning
  entity (`{"api_football": "12345"}`), never as columns baked into the primary schema — keeps
  provider replacement (architecture.md §5) from touching schema.

## 2. Core Sports Domain (`sports` schema) — extended Milestone 5

```
sports                    id, code (e.g. 'football'), name, status, version, provider_ref (JSONB)
countries                  id, code (ISO alpha-2), name, version, provider_ref (JSONB)      -- NEW M5
competitions               id, sport_id, name, type (league|cup|tournament), country, tier,
                          version, provider_ref (JSONB)
seasons                     id, competition_id, label, start_date, end_date, status,
                          version, provider_ref (JSONB)
teams                       id, sport_id, name, short_name, country, venue_id,
                          version, provider_ref (JSONB)
players                      id, sport_id, team_id (nullable — free agents), name, dob, position,
                          version, provider_ref (JSONB)
coaching_staff                id, team_id, person_name, role
officials                     id, sport_id, name, role
venues                        id, name, city, country, capacity, surface, timezone,
                          version, provider_ref (JSONB)
fixtures                      id, season_id, home_team_id, away_team_id, venue_id,
                              scheduled_at, status (scheduled|live|completed|postponed|cancelled),
                          version, provider_ref (JSONB)
matches                       id, fixture_id, started_at, ended_at, final_state (JSONB)
match_events                   id, match_id, minute/period, type, payload (JSONB), team_id, player_id
team_statistics                 id, match_id, team_id (unique together), stat_set (JSONB, sport-specific),
                          version, provider_ref (JSONB)
player_statistics                id, match_id, player_id, stat_set (JSONB, sport-specific)
lineups                        id, match_id, team_id (unique together), formation, slots (JSONB array
                          of {player_id, role, position, shirt_number}), version, provider_ref (JSONB) -- NEW M5
standings                        id, season_id, team_id, snapshot_at, rank, points, record (JSONB),
                          version, provider_ref (JSONB) -- one row per snapshot, history preserved
injuries                          id, player_id, reported_at, status, expected_return, source_ref
suspensions                       id, player_id, reason, start_date, end_date
transfers                         id, player_id, from_team_id, to_team_id, effective_date
rankings                          id, sport_id, scope (team|player), entity_id, system, value, as_of
```

`stat_set` / `payload` JSONB columns hold sport-specific shapes validated at the application
layer against per-sport Pydantic schemas (see [architecture.md](architecture.md) §4) — this is
the mechanism that lets Basketball and Table Tennis coexist in one relational schema without a
UNION of every possible column.

`version`/`provider_ref` were added to every entity Milestone 5 actively ingests (see the Entity
Expansion Matrix, §10) — bumped by `EntityReconciliationService` on every reconciled update, not
by a database trigger, so the domain layer controls exactly what counts as a "change" (formula:
if any user-visible field differs from the existing row, bump; a re-sync with identical data does
not bump). Entities Milestone 5 doesn't yet ingest (`coaching_staff`, `officials`, `match_events`,
`player_statistics`, `injuries`, `suspensions`, `transfers`, `rankings`) don't have these columns
yet — added when their ingestion is wired, per the same pattern.

## 3. Feature Intelligence Platform (`features` schema) — ✅ implemented, Milestone 4

```
feature_definitions       id, feature_key (unique), sport_code, category, description, formula,
                          data_type, unit, expected_range_low/high, update_frequency, owner,
                          entity_type, online_ttl_seconds, version, status, dependencies (JSON),
                          leakage_reviewed, reviewed_by, reviewed_at, rejection_reason, deprecated_at
feature_definition_versions  id, feature_key, version, snapshot (JSON), recorded_at
                          -- one row per *superseded* version, not one per version ever (ADR-014)
feature_values_offline     id, feature_key, entity_type, entity_id, as_of, value (JSON, typed), quality_flags
feature_lineage              id, feature_key, depends_on_feature_key
feature_drift_reports         id, feature_key, window, drift_score, method, detected_at
                          -- data model only; drift *computation* is Milestone 11
```

Maps directly to the documentation fields required in [feature_catalog.md](feature_catalog.md)
§"Feature Documentation". `sport_id` in the original sketch above became `sport_code` (matches
the `sports` module's `SportCode` string enum directly — no cross-schema FK needed for a value
that's already a small closed set).

**§9 open item resolved**: no `feature_values_online` Postgres mirror table — the online store
is Redis-only (`RedisFeatureStore`, TTL-bound cache), and `feature_values_offline` already is
the audited historical record. A cache miss falls back to the offline table, so there's no
scenario where a Postgres mirror would add anything the offline table doesn't already provide.

## 4. Prediction Intelligence Platform (`predictions` schema) — ✅ implemented, Milestone 9, extended Milestone 9.1

As actually shipped (migration `0018_prediction_intelligence_platform_schema`) — see
[prediction_engine.md](prediction_engine.md) and [prediction_markets.md](prediction_markets.md)
for the services/lifecycle behind each table. Differs from the original sketch in a few places:
`sport_id` → `sport_code` (matches every other module's `SportCode`-as-string convention, not a
cross-schema FK, same reasoning as `features.feature_definitions`); `market_kind` added (the
`MarketKind` taxonomy, [decisions.md](decisions.md) ADR-043); confidence/explanation are full
JSON structures, not a single scalar + a ref; no `fixture_id`/`entity_ref` columns — `subject_ref`
is a free-form string subsuming both, since a prediction's subject varies by sport/market.

```
prediction_markets           id, market_key (unique), sport_code, name, category, market_kind,
                             target_type (classification|regression), description,
                             min_historical_window_days, required_data_quality,
                             explainability_required, confidence_threshold,
                             status (draft|in_review|approved|production|deprecated|archived|removed),
                             owner, version, created_at, updated_at, reviewed_by, reviewed_at,
                             rejection_reason, deprecated_at
feature_market_mappings       id, market_id, feature_key, is_required, importance,
                             confidence_contribution, weight
models                        id, market_id, model_key, version, algorithm,
                             status (candidate|challenger|champion|retired),
                             training_dataset_ref, calibration_ref, approved_by, approved_at,
                             promoted_at, retired_at, created_at,
                             -- Milestone 9.1 additive (migration 0023):
                             framework, dataset_version, feature_versions (JSON),
                             training_run_ref, calibration_report_ref, feature_importance_ref,
                             artifact_ref, deployment_mode, trained_at
predictions                    id, market_id, model_id, subject_ref, value, probability,
                             confidence (JSON, full 9-factor breakdown), explanation (JSON, full
                             bundle), feature_snapshot (JSON), model_version,
                             status (draft|published|superseded|voided), generated_at,
                             data_freshness
prediction_outcomes              id, prediction_id (unique), actual_value, error, evaluated_at
model_evaluations                 id, model_id, evaluated_at, metrics (JSON), calibration_report (JSON)
experiments                        id, market_id, config (JSON), metrics (JSON), decision, created_at
prediction_audits                   id, action, actor, occurred_at, prediction_id, market_id,
                                  model_id, details (JSON)
```

**Milestone 9.1** (migration `0023_ml_platform_schema`, ✅ applied live 2026-07-26 — see
[rls.md](rls.md) §6c) adds 7 tables:

```
datasets                     id, market_id, version, content_hash, samples (JSON),
                             statistics (JSON), lineage (JSON), quality_issues (JSON),
                             status (draft|validated|approved|archived), created_at,
                             approved_by, approved_at
training_runs                 id, market_id, model_id, dataset_id, algorithm, framework,
                             train_metrics (JSON), test_metrics (JSON), feature_order (JSON),
                             selected_features (JSON), samples_used, outliers_removed,
                             started_at, completed_at
calibration_reports            id, model_id, method, sample_count, expected_calibration_error,
                             brier_score, reliability_curve (JSON), generated_at
feature_importance_reports      id, model_id, global_importance (JSON), computed_at
latency_samples                 id, market_id, duration_ms, recorded_at
retraining_jobs                  id, market_id, status (pending|...), trigger_reason (JSON),
                             created_at, completed_at
model_artifacts                   id, model_id, storage_ref, content_hash, size_bytes, created_at
```

## 5. Knowledge Graph (`knowledge_graph` schema) — ✅ implemented, Milestone 5 (population only)

Modeled relationally with an edge table rather than a dedicated graph DB for v1
([ADR-005](decisions.md); revisit if traversal patterns outgrow Postgres recursive CTEs):

```
kg_nodes      id, node_type, entity_ref (string — internal entity id), attributes (JSONB)
              unique on (node_type, entity_ref)
kg_edges      id, from_node_id, to_node_id, edge_type, weight, attributes (JSONB), valid_from, valid_to
```

`node_type` now includes `country` (added in Milestone 5, alongside the original set from
[knowledge_graph.md](knowledge_graph.md) §2). `edge_type` gained two Milestone 5 additions —
`belongs_to` (generic hierarchical containment) and `located_in` (entity → country) — see
[knowledge_graph.md](knowledge_graph.md) §3 and [ADR-019](decisions.md). Population only: no
query/traversal/similarity layer exists yet (Milestone 9).

## 6. Identity & Billing (`identity`, `billing` schemas)

```
identity.users             id (mirrors Supabase auth.users id), email, display_name, role
identity.roles                id, name, permissions (JSONB)
identity.sessions              -- delegated to Supabase Auth, not duplicated here

billing.subscriptions        id, user_id, tier (free|premium|enterprise), status, renews_at
billing.ad_unlocks             id, user_id, granted_at, expires_at, source (rewarded_ad)
billing.usage_counters          user_id, period, ai_requests_used, ai_requests_limit
```

## 7. Content & Community (`content` schema)

```
news_items          id, source, url, published_at, raw_text, reliability_score
news_events           id, news_item_id, event_type, entity_refs (JSONB), confidence_score
community_posts        id, platform, entity_refs (JSONB), sentiment, reliability_score, posted_at
```

## 8. Row-Level Security Strategy

- `identity.*`, `billing.*`, personalization tables: RLS on, owner-scoped.
- `sports.*`, `features.*`, `predictions.*`, `knowledge_graph.*`: RLS on with a public-read
  policy for published data and a service-role bypass for ingestion workers — never
  application-layer-only enforcement.
- Admin tables (`admin.*`): RLS restricted to `role = 'admin'` claim.

## 9. Open Items

- Confirm partitioning strategy for `match_events` / `feature_values_offline` once volume
  estimates exist (likely time-range partitioning per season).
- ~~Decide whether `feature_values_online` needs to exist in Postgres~~ — resolved in Milestone
  4, §3 above: Redis-only, no Postgres mirror ([ADR-008](decisions.md) pattern).
- Confirm table-tennis-specific statistics shape (no provider selected yet — see
  [titaniq.md](titaniq.md) §6).

## 10. Sports Data Ingestion Platform (`ingestion` schema) — ✅ implemented, Milestone 5

```
sync_runs             id, sport_code, entity_kind, scope_key, trigger, status, started_at,
                     finished_at, records_fetched/created/updated/rejected, validation_failures,
                     error_message
sync_checkpoints        id, sport_code, entity_kind, scope_key (unique together), last_synced_at,
                     last_success_at, cursor, consecutive_failures
                     -- "never reload complete datasets unnecessarily": SyncOrchestrator checks
                     -- this before every non-LIVE sync and skips if still within the interval
timeline_events           id, event_type, occurred_at, actor, sport_code, entity_kind, entity_id,
                     payload (JSONB) — append-only, never updated (Event Timeline Engine, also
                     doubles as the ingestion audit log, see ADR-020)
data_quality_reports        id, sport_code, entity_kind, generated_at, sample_size,
                     completeness/consistency/freshness/accuracy/validity/reliability/coverage/
                     provider_quality/quality scores (all nullable floats), issues (JSON array)
provider_ref_index          id, provider, external_id, entity_kind (unique together with the
                     first two), entity_id — O(1) "have we seen this external id before" lookup,
                     avoiding a scan of every entity's provider_ref JSON column (ADR-021)
```

## 11. Entity Expansion Matrix (docs/roadmap.md Milestone 5)

Every canonical entity the constitution names, and its actual ingestion status as of Milestone
5. "Fully wired" means: provider DTO exists, `EntityValidationEngine` validates it,
`EntityReconciliationService` reconciles it with versioning + provider tracking, KG population
runs, and it has dedicated tests. Adding a not-yet-wired entity is mechanical (same pattern,
new DTO + reconciler method) — this table is what Milestone 6+ work should consult before
building a prediction market that depends on an entity still marked "not wired."

| Entity | Domain model (M2) | Provider DTO | Reconciler | KG node | Status |
|---|---|---|---|---|---|
| Sport | ✅ | n/a (seeded from plugin registry) | ✅ | ✅ | **Fully wired** |
| Competition | ✅ | ✅ (`competition_ref`) | ✅ | ✅ | **Fully wired** |
| Country | ✅ (M5) | ✅ | ✅ | ✅ | **Fully wired** |
| Season | ✅ | ✅ (`season_label`) | ✅ | ✅ | **Fully wired** |
| Venue | ✅ | partial (name only, no dedicated DTO) | ✅ (synthetic ref key) | ✅ | **Fully wired**, with a noted limitation (§ below) |
| Team | ✅ | ✅ | ✅ | ✅ | **Fully wired** |
| Player | ✅ | ✅ | ✅ | ✅ | **Fully wired** |
| Fixture | ✅ | ✅ | ✅ | ✅ (as `match` node) | **Fully wired** |
| Match Statistics (TeamStatistics) | ✅ | ✅ | ✅ | ✅ (as `statistics` node) | **Fully wired** |
| Lineup | ✅ (M5) | ✅ | ✅ | not yet (embedded in match/player edges only via future work) | **Fully wired** |
| Standing | ✅ | ✅ | ✅ (snapshot-per-sync) | ✅ (edge attribute, no dedicated node) | **Fully wired** |
| Rounds | ❌ | ❌ | ❌ | ❌ | Not started |
| Coaches (coaching_staff) | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Officials | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Player Statistics | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Injuries | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Suspensions | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Transfers | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Rankings | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only |
| Match Events (goal/card/etc.) | ✅ (M2) | ❌ | ❌ | ❌ | Domain model only — `TimelineEvent` covers the *ingestion lifecycle* vocabulary (kickoff, goal, card, ...) as event *types*, but nothing populates `match_events` from a live provider feed yet |
| Historical Results | — | — | — | — | Not a distinct entity — historical fixtures/statistics use the same tables as live ones, distinguished by `status`/`snapshot_at`; explicit historical *backfill* scheduling is Milestone 5's `HISTORICAL_IMPORT_INTERVAL_SECONDS` policy, not a separate schema |

**Venue limitation**: providers in this codebase give only a `venue_name` string (no distinct
venue id), so Venue reconciliation keys off a synthetic `f"venue:{name}"` ref rather than a real
provider id — correct as long as two different venues never share an exact name string within
one provider. A real venue-id-bearing provider field would remove this constraint without any
other architectural change (docs/decisions.md — pending future ADR if this becomes a problem).

**Roadmap gate**: no Milestone 6+ prediction market may declare a dependency on a "Domain model
only" or "Not started" entity above without first promoting it to "Fully wired" — see
[roadmap.md](roadmap.md) Milestone 5 entry.
