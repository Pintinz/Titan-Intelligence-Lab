# Milestone 9 Verification Report — News Intelligence Foundation & Market-Specific Impact Engine

## 0. Scope and governing rule

This milestone builds a formal provenance, confidence, entity-resolution, and market-specific
impact layer on top of the real (non-mock) news ingestion pipeline that already existed from
Milestone 8. It does **not** enable a production news-ingestion schedule, does **not** retrain or
promote any model, does **not** activate Community Intelligence, and does **not** backfill history
for events whose real availability time cannot be honestly reconstructed.

**Final governing rule** (verbatim from the spec, restated here as the acceptance bar): TitanIQ
must never confuse "news exists" with "news was known before the prediction." Only information
demonstrably available before the relevant event may influence prediction intelligence.
Market-specific relevance is mandatory. Confidence is mandatory. Temporal provenance is mandatory.
Entity resolution is mandatory. No fabricated intelligence. No uncontrolled learning. No training
during inference. No production model promotion during this milestone.

## 1. Investigation findings (mandatory pre-work, not assumed from prior docs)

Before writing any code, the current state of the news pipeline was inspected directly — via a
dedicated Explore agent reading real source files and the live `dev.db` — rather than trusting the
spec's own framing that no real provider exists.

- **Two real, non-mock providers exist**: `RssNewsProvider` (real RSS parsing) and `GeminiAdapter`
  (real, credentialed, active in `dev.db`'s `intelligence.news_sources` config). `MockGeminiAdapter`
  is a distinct, test/dev-only implementation of the same port — it is never wired into the real
  admin sync endpoint. This corrected what would otherwise have been an incorrect STOP under the
  spec's "do not fabricate a provider" rule — a provider already exists; nothing was fabricated
  here.
- **The real, root-caused bug**: `EventExtractionService.extract_and_record` built
  `affected_entity_refs` as `raw.entities + resolved_refs` — the provider's own *unresolved* NER
  tags (from `extract_events`, where `MockGeminiAdapter` hardcodes literal `"mock_player"`/
  `"mock_team"`/`"mock_coach"` strings for test purposes) merged directly with the separately,
  properly KG-resolved refs from `EntityExtractionService.extract_and_link`, with no way for any
  downstream consumer to tell which was which. This is exactly how an unresolved placeholder string
  could reach a field every consumer assumed was a real Knowledge Graph node id.
- **68 pre-existing `news_events` rows**, all MockGeminiAdapter-originated per
  `docs/milestone3_historical_data_audit.md`, all lacking any of the fields this milestone adds.
  Deliberately left as-is — never reclassified, never backfilled as verified (see §12).
- **No Celery Beat schedule exists for news** — `enrich_article`'s only real caller today is the
  admin-triggered manual sync endpoint (`apps/api/main.py`'s `trigger_news_sync`). This means every
  event extracted through the real pipeline today is `MANUAL`-triggered, and — by this milestone's
  own new rule (§7) — correctly lands at `UNKNOWN_AVAILABILITY_TIME`, never fabricated as verified
  merely because a real (non-mock) provider produced it.

## 2. Why this scope, and what changed from the initial assumption

The spec's own framing implied a fresh news pipeline might be needed. It was not — Milestone 8
already built real extraction (`EventExtractionService`), real impact scoring (`NewsImpactEngine`),
real source reliability (`SourceReliabilityService`), and a real orchestrator wiring them together.
This milestone's job was narrower and more surgical: fix the one real entity-resolution bug, add
the formal provenance/confidence/temporal-validity layer that milestone 8 never had, and build the
market-specific impact engine the spec's §10-11 explicitly requires — not rebuild ingestion.

## 3. Files changed

**Domain / value objects**
- `modules/intelligence/domain/entities.py` — new `ResolvedNewsEntity`; `NewsEvent` extended with
  `resolved_entities`, `confidence_tier`, `information_available_at`, `availability_classification`,
  `validity_start`, `validity_end`, `sync_run_id`, and the `is_feature_eligible()` choke point.
- `modules/intelligence/domain/value_objects.py` — `SyncTrigger.LIVE_SCHEDULED` added (mirrors
  `modules.ingestion`'s rule without importing it — `IntelligenceSyncRun`'s own docstring already
  establishes this module never imports `modules.ingestion`); new `EntityResolutionStatus`,
  `NewsEventConfidenceTier` enums.

**Application services**
- `modules/intelligence/application/news_provenance.py` (new) — `classify_news_availability`,
  `NewsEventConfidenceClassifier`, `CONFIDENCE_WEIGHT_MULTIPLIERS`.
- `modules/intelligence/application/news_validity_policy.py` (new) — per-event-type TTL windows.
- `modules/intelligence/application/event_extraction_service.py` — `extract_and_record` rewritten:
  `resolved_entities` built from the real `EntityExtractionService.extract_and_link` output only;
  `affected_entity_refs` is now RESOLVED-only, restoring its originally-intended contract.
- `modules/intelligence/application/intelligence_enrichment_orchestrator.py` — `enrich_article`
  gained `trigger`/`sync_run_id` params; new `_classify_and_persist` (confidence tier + availability
  classification, re-persists the event) and `_corroboration` (real, from
  `NewsEventRepositoryPort.list_for_entity`, narrow `INJURY↔RECOVERY` contradiction detection); every
  `_publish_event_features` call now gated on `event.is_feature_eligible()`.
- `modules/predictions/application/news_market_impact_registry.py` (new) — `MarketImpactRule`,
  `MARKET_IMPACT_RULES` (8 representative rules), `PLAYER_ROLE_BY_POSITION`/`normalize_player_role`.
- `modules/predictions/application/news_market_impact_engine.py` (new) — `NewsMarketImpactEngine`:
  roster → KG node → events → rule-match → confidence-weighted sum, per side, per dimension.

**Wiring**
- `modules/ingestion/application/entity_reconciliation_service.py` — `news_market_impact_engines`
  dict field + `_compute_news_market_impact`, called from `reconcile_fixture` after the existing
  transfer-activity computation.
- `modules/predictions/football/market_seeding.py` — `_NEWS_GOAL_IMPACT_FEATURES`/
  `_NEWS_CLEAN_SHEET_IMPACT_FEATURES`/`_NEWS_BTTS_IMPACT_FEATURES` constants; spliced into
  `required_features` of the 12 target markets (see §8); `ensure_registered` call added to `seed()`.
- `apps/api/composition.py` — `build_football_news_market_impact_engine`; wired into
  `build_football_market_seeder` and `build_entity_reconciliation_service`.
- `apps/api/main.py` — `trigger_news_sync` passes `trigger=SyncTrigger.MANUAL` explicitly (the
  admin endpoint's honest trigger type).

**Database**
- `alembic/versions/0041_milestone9_news_provenance.py` (new) — additive-only migration, 7 new
  `intelligence.news_events` columns, honest `server_default`s.
- `scripts/apply_migration_0041_news_provenance.py` (new) — direct application script for SQLite
  dev.db (see §4 for why `alembic upgrade head` doesn't apply cleanly here).

**Tests** — 6 new test files, 2 updated test files (see §14).

## 4. Database changes

`alembic upgrade head` does not cleanly apply migration 0041 against the local SQLite `dev.db`,
because migration 0041 declares `schema="intelligence"` (a Postgres schema) and
`alembic/env.py`'s `run_migrations_online()` doesn't set a `schema_translate_map` the way the real
app engine (`modules.sports.infrastructure.persistence.database.build_engine`) does — the same gap
Milestone 5 hit and worked around. `scripts/apply_migration_0041_news_provenance.py` uses that same
schema-translate-map-aware engine and applies the equivalent DDL directly. Idempotent (checks
`PRAGMA table_info` before each `ADD COLUMN`), so safe to re-run.

`dev.db` was backed up to `dev.db.bak-before-milestone9-news-provenance` before running. Applied
result, verified directly:

```
added column: resolved_entities
added column: confidence_tier
added column: information_available_at
added column: availability_classification
added column: validity_start
added column: validity_end
added column: sync_run_id
news_events total=68, availability_classification=UNKNOWN_AVAILABILITY_TIME=68
```

All 68 pre-existing rows — none synced through a genuine `LIVE_SCHEDULED`-equivalent pipeline —
honestly land at `UNKNOWN_AVAILABILITY_TIME`, `confidence_tier='uncertain'`, `resolved_entities='[]'`.
None reclassified as verified, none backfilled with a fabricated timestamp.

## 5. Event Confidence Taxonomy

Six formal tiers (`NewsEventConfidenceTier`): CONFIRMED / PROBABLE / UNCERTAIN / RUMOUR /
CONTRADICTED / EXPIRED. `NewsEventConfidenceClassifier.classify` applies them in this exact,
deterministic priority order:

1. `contradicted` → CONTRADICTED (overrides everything, including an official source)
2. `age_hours > ttl_hours` → EXPIRED (overrides an official source too)
3. `is_official_source` → CONFIRMED
4. `source_trust_level >= VERIFIED` and `corroborating_source_count >= 1` → PROBABLE
5. `event_type == TRANSFER` and `source_trust_level <= UNVERIFIED` and
   `corroborating_source_count == 0` → RUMOUR (transfer-speculation-specific, per the spec's own
   distinct example — a non-TRANSFER event in the same situation is UNCERTAIN, not RUMOUR)
6. else → UNCERTAIN

`CONFIDENCE_WEIGHT_MULTIPLIERS` (spec §5's own example table): CONFIRMED=1.0, PROBABLE=0.6,
UNCERTAIN=0.3, RUMOUR=0.1, CONTRADICTED=0.0, EXPIRED=0.0.

Corroboration/contradiction are computed from real, already-persisted data
(`IntelligenceEnrichmentOrchestrator._corroboration`) — distinct-other-source count sharing the
same `event_type` for a shared resolved entity, and a narrow, honest opposed-type table
(`{INJURY: RECOVERY, RECOVERY: INJURY}` — the only genuinely unambiguous opposite pair in
`NewsEventType`). No fabricated NLP sentiment/opposition model.

## 6. Entity resolution fix

`resolved_entities` (the new authoritative field) is populated exclusively from
`EntityExtractionService.extract_and_link` — real NER + `EntityResolutionService.find_by_alias`
Knowledge Graph matching — each entry tagged `RESOLVED` or `UNRESOLVED`. `affected_entity_refs` is
now derived as RESOLVED-only. Provider-side raw entity tags from `extract_events` (e.g.
`MockGeminiAdapter`'s literal `"mock_player"`/`"mock_team"`) never enter this pipeline at all — not
merged in unresolved, not silently dropped as UNRESOLVED either, since they were never real NER
mentions in the first place. Verified with a dedicated test
(`test_extract_and_record_keeps_affected_entity_refs_resolved_only`) proving the mock strings never
appear anywhere on the resulting event.

`NewsEvent.is_feature_eligible()` requires `availability_classification == VERIFIED_PRE_MATCH` AND
`all(e.status is RESOLVED for e in resolved_entities)` — an event with even one UNRESOLVED entity
(vacuously true if there are zero entities at all) never contributes to a feature.

## 7. Temporal validity / provenance rules

`classify_news_availability` (mirrors `modules.ingestion.application.provenance.classify_availability`'s
rule, adapted for news's non-fixture-bound shape — no kickoff/prematch-window gate, same reasoning
already applied to `Transfer`):

- Not validated → `INVALID`
- Sync failed → `UNKNOWN_AVAILABILITY_TIME`
- `trigger != LIVE_SCHEDULED` → `UNKNOWN_AVAILABILITY_TIME` (this is the rule that keeps every
  today's-real-world event at `UNKNOWN_AVAILABILITY_TIME`, since no Beat schedule exists — see §1)
- No genuine timestamp → `UNKNOWN_AVAILABILITY_TIME`
- All four conditions pass → `VERIFIED_PRE_MATCH`, `information_available_at = published_at`
  (never `detected_at`/`fetched_at`/`now` as a substitute)

Per-event-type validity windows (`news_validity_policy.validity_window_hours`, env-overridable, all
14 `NewsEventType` members covered, no silent fallback to a generic default for a real type):
TRANSFER 90d, INJURY 14d, RECOVERY 7d, SUSPENSION 21d, MANAGER_CHANGE 180d, FORMATION/
TACTICAL_CHANGE 14d, TRAINING_UPDATE 3d, WEATHER_REPORT 3d, TRAVEL_DELAY 2d, STADIUM_CHANGE 30d,
MATCH_POSTPONEMENT 14d, PLAYER_AVAILABILITY 7d, LINEUP_EXPECTATION 3d (shortest — speculative by
nature).

## 8. Market-Specific Impact Engine

Explicitly **not** one generic score applied to every market. `NewsMarketImpactEngine` computes
three distinct, market-specific feature dimensions per side (home/away) —
`news.football.{home,away}_{goal_impact,clean_sheet_impact,btts_impact}` — from
`MARKET_IMPACT_RULES` (8 representative rules, forward and goalkeeper roles): roster (`Player`) →
Knowledge Graph node → feature-eligible events for that node → rule match (`event_type` +
`entity_role`) → still-within-`ttl_hours`-at-*read*-time → `direction * magnitude *
CONFIDENCE_WEIGHT_MULTIPLIERS[confidence_tier]`, summed per dimension.

Null semantics mirror `TransferActivityCalculator` (Milestone 7) exactly: zero relevant
feature-eligible events → writes nothing (`None`, unavailable); evidence exists but nets to zero
(e.g. an injury and a recovery on the same forward, roughly offsetting) → writes a genuine `0.0`.

Wired into `EntityReconciliationService.reconcile_fixture` (via `news_market_impact_engines`, keyed
by sport code) right after the existing transfer-activity computation — fires on every real
reconciliation, same trigger point as every other M6-M8 engineered feature.

## 9. Market Impact Registry — feature-to-market wiring (verified against dev.db)

Unlike Milestone 8's heuristic-market *optional* wiring, every one of the three news dimensions
targets only markets already among the 14 genuinely-trained football markets — so these are wired
as plain **required** features (the seeder's default), the same "inert until a future retrain"
posture Milestones 6/7 established for a live Champion.

| Dimension | Feature keys | Target markets |
|---|---|---|
| goal_impact | `news.football.{home,away}_goal_impact` | `total_goals_over_under` (+0.5/1.5/3.5/4.5), `home_team_total_goals`, `away_team_total_goals` (7 markets) |
| clean_sheet_impact | `news.football.{home,away}_clean_sheet_impact` | `home_clean_sheet`, `away_clean_sheet`, `home_win_to_nil`, `away_win_to_nil` (4 markets) |
| btts_impact | `news.football.{home,away}_btts_impact` | `both_teams_to_score` (1 market) |

Re-ran `scripts/seed_football_markets.py` against `dev.db` (after backing it up to
`dev.db.bak-before-news-market-seed`) — completed with no errors. Direct SQL verification:

```
-- feature_definitions: all 6 news.football.* keys, status=active, leakage_classification=PRE_MATCH_SAFE
-- feature_market_mappings: 24 rows total (7×2 + 4×2 + 1×2), is_required=1, weight=1.0,
--   exactly matching the table above — zero leakage into football.correct_score or
--   football.match_winner (checked directly, both absent from the mapping set)
```

## 10. Feature Store integration & leakage classification

Every feature key registered via `NewsMarketImpactEngine.ensure_registered` gets
`FeatureCategory.AI_EXTRACTED`, `EntityType.FIXTURE`, a 24-hour online TTL, and
`leakage_classification = "PRE_MATCH_SAFE"` — earned because every contributing event is already
required to pass `is_feature_eligible()` (VERIFIED_PRE_MATCH) before it can contribute anything, the
same gating every other M6-M8 point-in-time-safe feature relies on.

## 11. Avoiding duplication with structured intelligence; precedence

News-derived features are additive, not a replacement for structured injury/transfer/lineup data
(Milestones 5-7's `LineupContinuityCalculator`/`TransferActivityCalculator`, and the pre-existing
structured `Injury`/`Transfer` entities). They occupy a distinct feature-key namespace
(`news.football.*` vs `football.fixture.*`) and a distinct event source (unstructured news text vs
structured provider feeds) — no market required-feature list references both a news-derived and a
structured-intel feature for the *same* underlying signal. Precedence is implicit and structural:
structured intelligence (provider-confirmed injuries/transfers/lineups) already has its own
independent, higher-trust ingestion path and is never overridden by a news-derived signal — the two
simply compose as separate additive terms in each market's feature set.

## 12. Production safety — explicit confirmations

- **No retrain.** No `AutomaticModelSelectionService` invocation, no dataset rebuild, anywhere in
  this milestone's code.
- **No promotion.** No `ModelRegistryService.promote_to_challenger`/`promote_to_champion` call.
- **No fabricated history.** The 68 pre-existing mock-originated `news_events` rows were never
  reclassified, never backfilled with a fabricated `information_available_at`; every row still
  reads `availability_classification='UNKNOWN_AVAILABILITY_TIME'` after migration (§4).
- **No enabling Community Intelligence.** Not touched anywhere in this milestone — its interface
  remains intact and disabled, exactly as instructed.
- **No mock news in production path.** `MockGeminiAdapter` was not touched and is not reachable
  from `trigger_news_sync` (the only real admin sync endpoint) — confirmed by direct code read in
  §1.
- **No leakage.** Every news feature requires `is_feature_eligible()` (VERIFIED_PRE_MATCH + fully
  resolved entities) before writing anything; `leakage_classification="PRE_MATCH_SAFE"` earned, not
  assumed.

## 13. Ablation readiness (metadata only — evaluation deferred)

Every feature this milestone registers already carries a versioned `feature_key`, a formula
description, and a leakage classification via the existing Feature Registry — the same metadata
substrate every prior milestone's engineered feature uses for eventual ablation study. No actual
ablation evaluation (measuring model performance with/without the news dimensions) was run this
milestone — deferred to a later milestone once enough real, VERIFIED_PRE_MATCH-eligible events
exist to matter (today: zero, since no LIVE_SCHEDULED sync exists yet — see §16).

## 14. Tests added

**New files** (37 new tests):
- `tests/unit/modules/intelligence/test_news_provenance.py` (13) — availability classification (6
  cases) + confidence classifier (7 cases, including tier-priority-order and the
  TRANSFER-specific-RUMOUR distinction).
- `tests/unit/modules/intelligence/test_news_validity_policy.py` (4) — per-type windows + full
  enum coverage (no silent default fallback).
- `tests/unit/modules/intelligence/test_news_event_feature_eligibility.py` (5) —
  `NewsEvent.is_feature_eligible()` truth table.
- `tests/unit/modules/predictions/test_news_market_impact_registry.py` (8) — role normalization,
  rule TTL/direction/magnitude sanity, the 3-dimension market-specificity claim itself.
- `tests/unit/modules/predictions/test_news_market_impact_engine.py` (7) — registration, null
  semantics (no-evidence vs genuine-zero), non-eligible-event exclusion, TTL-expiry exclusion,
  confidence-tier magnitude scaling, injury+recovery evidence-but-nonzero write.

**Updated files** (5 new tests, 2 tests fixed to reflect the new correct — not the old buggy —
behavior):
- `tests/unit/modules/predictions/test_football_market_seeding.py` — 5 new tests verifying the §9
  wiring (required=True on every target market, correct feature-to-market grouping, no leakage into
  unrelated markets, feature registration with `PRE_MATCH_SAFE`).
- `tests/unit/modules/intelligence/test_event_extraction_service.py` — the one test that asserted
  the pre-fix behavior (`"mock_player" in affected_entity_refs`) rewritten to assert the fixed
  behavior instead (§6).
- `tests/unit/modules/intelligence/test_intelligence_enrichment_orchestrator.py` — fixture helper
  updated to pass `events=` (the orchestrator's new required field) and `mention_text`/
  `mention_type` so entity resolution genuinely succeeds under the new resolved-entities-only
  contract; 5 tests updated to pass `trigger=SyncTrigger.LIVE_SCHEDULED` explicitly, since they test
  the feature-eligible path and the orchestrator's default (`MANUAL`) never reaches
  `VERIFIED_PRE_MATCH` (§7) — this is intentional new safety behavior, not a workaround.

**Total: 42 new test functions**, all passing.

## 15. Full test results

```
2066 passed, 58 skipped, 0 failed, 4 warnings in 1232.77s (0:20:32)
```

## 16. Regression comparison against M8 baseline

| | M8 baseline | M9 result | Delta |
|---|---|---|---|
| Passed | 2024 | 2066 | +42 (exactly the new test count in §14) |
| Skipped | 58 | 58 | 0 |
| Failed | 0 | 0 | 0 |

No pre-existing test needed a behavior change except the two explicitly documented in §14 (both
because they encoded the pre-fix buggy behavior or the pre-M9 unconditional-publish behavior this
milestone intentionally replaced with a safety gate).

## 17. Known limitations & deliberate scope exclusions

- **No real Celery Beat schedule for news exists yet.** Deliberate, self-initiated scope decision:
  every prior M4-M8 change touched only internal SQLite state; a recurring news sync would be the
  first genuinely recurring, cost-incurring external-API call in this sequence. `enrich_article`'s
  `trigger` defaults to `MANUAL`, matching its only real caller today. Consequence: **every
  real-world news event extracted today lands at `UNKNOWN_AVAILABILITY_TIME`**, and by design
  `NewsMarketImpactEngine` therefore currently contributes nothing to any live prediction — inert
  until a `LIVE_SCHEDULED`-triggered sync path is built in a later milestone, then re-verified.
- **8 representative Market Impact Rules, not exhaustive.** Two roles (forward, goalkeeper), three
  event types (INJURY/SUSPENSION/RECOVERY) — the same ADR-narrowing posture as every other v1
  component in this codebase (M6's one feature, M7's scoped rule set, M8's 4-market scope).
  Extending to more roles/markets is additive, no existing rule changes shape.
- **Contradiction detection is narrow.** Only the one genuinely unambiguous opposed-type pair
  (`INJURY`↔`RECOVERY`). Broader same-claim-conflicting-details detection needs real NLP comparison
  — not fabricated here.
- **No ablation evaluation run** (see §13) — deferred, and moot today anyway since no
  VERIFIED_PRE_MATCH-eligible real event exists yet.

## Acceptance checklist

- [x] Real, non-mock provider architecture confirmed present — nothing fabricated (§1)
- [x] The one real entity-resolution bug root-caused and fixed, with a test proving the fix (§6)
- [x] 6-tier Event Confidence Taxonomy built, deterministic, spec-example-consistent (§5)
- [x] Temporal validity: `information_available_at` never fabricated; only `LIVE_SCHEDULED` +
      genuine timestamp can ever produce `VERIFIED_PRE_MATCH` (§7)
- [x] Event-type-specific validity windows, documented rationale, full enum coverage (§7)
- [x] Market-Specific Impact Engine — 3 distinct dimensions, not one generic score (§8)
- [x] Market Impact Registry with the spec's required per-rule fields (§9)
- [x] Feature Registry entries with correct `PRE_MATCH_SAFE` leakage classification (§10)
- [x] No duplication with existing structured injury/transfer/lineup intelligence (§11)
- [x] Community Intelligence untouched, still disabled (§12)
- [x] No retrain, no promotion, no fabricated history, no mock news in production path (§12)
- [x] Ablation-readiness metadata present; actual evaluation correctly deferred (§13)
- [x] ≥20 new tests (42 delivered) (§14)
- [x] Full suite run and compared against M8 baseline — 0 failed, 0 regressions (§15-16)
- [x] `dev.db` verified directly: migration applied, 68/68 legacy rows honestly
      `UNKNOWN_AVAILABILITY_TIME`, 6 feature keys + 24 market mappings correctly wired (§4, §9)

## Stop condition

Milestone 9 is complete and verified. Per the governing process and the user's own explicit closing
instruction: **STOP. Do not begin Milestone 10 automatically. Wait for explicit approval.**
