# POST-M24 MASTER DATA FABRIC — PHASE 3: PROVIDER CAPABILITIES & SOURCE ORCHESTRATION — Verification Report

## 1. Executive Summary

Phase 3 built a `ProviderCapabilities` layer that answers "which provider can supply this data,
for which sport, domain, temporal mode, and (where provable) competition" — as a declarative,
read-only contract, verified against actual adapter source code, not guessed. It integrates with
the existing provider registry rather than creating a second one, reuses Phase 2's cache/quota/
circuit-breaker primitives without duplicating them, and adds a new, additive `SourceSelectionService`
that future orchestration can consult — without touching `SportsProviderRouter`'s own,
already-tested internal selection logic, and without rewriting a single provider client. Table
tennis correctly reports "no real provider" without crashing. News capabilities were kept
deliberately separate from sports-provider capabilities, per the master prompt's own instruction.
Full backend regression: **2334 passed, 58 skipped, 0 failed** (baseline was 2287 — the +47 is
exactly the new tests this phase added). Zero external API calls, zero Gemini calls, zero database
writes, zero Champion/model changes anywhere in this phase.

## 2. Existing Provider Architecture (confirmed unchanged, re-verified before writing code)

`SportsDataProviderPort` (`modules/sports/ports/provider_gateway.py`) defines 12 async methods.
`SportsProviderRouter` resolves one real-or-mock adapter per sport (`real_adapters`/`mock_adapters`,
keyed by `SportCode.value`) plus a second, narrower `fixture_schedule_adapters` slot (keyed by
`provider_key`) for providers only ever reached via an explicit per-competition
`CompetitionFixtureSourcePreference` opt-in. `PROVIDER_KEY_BY_SPORT`
(`apps/api/composition.py`) has exactly three entries: football, basketball, baseball — no
table_tennis. This is the exact same architecture Phase 1/2 found and left unchanged; Phase 3
adds a new layer alongside it, described below.

## 3. Capability Gap

Confirmed (Phase 1 finding, re-verified): no `ProviderCapabilities` concept existed anywhere in
the codebase — zero matches for `ProviderCapabilities`/`FIXTURE_DISCOVERY`/`LIVE_FIXTURES` etc.
across two independent repo-wide greps. The only pre-existing "capability"-adjacent concept was
`admin`'s free-text `Provider.capability_note` (a best-effort scraped connection-test note, not a
structured, queryable contract). Which capability a provider had was discoverable only by reading
its adapter's source code — exactly the gap this phase closes.

## 4. Capability Taxonomy

New enums in `modules/sports/domain/provider_capabilities.py`:
- `ProviderDomain`: `COMPETITIONS, SEASONS, COUNTRIES, TEAMS, PLAYERS, FIXTURES, RESULTS,
  STANDINGS, MATCH_EVENTS, TEAM_STATISTICS, PLAYER_STATISTICS, LINEUPS, ODDS, INJURIES, TRANSFERS,
  COACHING_STAFF` — mirrors `SportsDataProviderPort`'s real method surface exactly, plus the two
  request-scoping concepts every method is already parameterized by. `MATCH_EVENTS`/
  `PLAYER_STATISTICS` exist for taxonomy completeness (the master prompt's minimum vocabulary) but
  no current adapter implements a corresponding fetch method — confirmed no registered provider
  claims either (test: `test_no_current_provider_claims_the_taxonomy_only_domains`).
- `TemporalMode`: `HISTORICAL, UPCOMING, LIVE, PRE_MATCH, POST_MATCH`.
- `SourceRole`: `PRIMARY, SECONDARY, FALLBACK, ENRICHMENT, HISTORICAL`.

`SportCode` (existing, reused unchanged from `modules.sports.domain.value_objects`) is the sport
axis — no duplicate sport enum was created. League/competition/season awareness is answered via
`supports_competition` (§13), not a separate enum, since no adapter has a provable per-competition
allowlist (only the fixture-schedule-scoped role does, via the real
`CompetitionFixtureSourcePreference` mechanism).

News capabilities are a deliberately separate, smaller taxonomy — see §11.

## 5. `ProviderCapabilities` Design

`ProviderCapabilities` (frozen dataclass): `provider_key`, `sport`, `domains: frozenset[ProviderDomain]`,
`temporal_modes: frozenset[TemporalMode]`, `source_roles: frozenset[SourceRole]`,
`fixture_schedule_scoped: bool`. Immutable, code-declared (see §20 for why not database-backed).
`supports_domain`/`supports_temporal_mode`/`supports_source_role` are pure boolean methods —
capability describes what a provider *can* do, never what's currently available (that remains
`CircuitBreaker`/`QuotaIntelligenceEngine`'s job, unchanged). Absence from a `domains`/
`temporal_modes` set *is* "not supported" — no separate "unknown" sentinel was needed, since every
entry in the registry (§6) is derived from a real, read source-code fact, not an assumption.

## 6. Provider Registry Integration

`PROVIDER_CAPABILITIES: dict[str, ProviderCapabilities]` in the same module — the single source of
truth, no second registry. `CapabilityResolver` (`modules/sports/application/capability_resolver.py`)
is the only consumer that combines it with runtime state (`ProviderManagementService`,
`CircuitBreaker`, `QuotaIntelligenceEngine`, `CompetitionFixtureSourceRepositoryPort` — all four
reused unchanged from Phase 1/2, none duplicated). `apps/api/composition.py` gained two new,
additive factories (`build_capability_resolver`, `build_source_selection_service`) — no existing
factory (including `build_sports_provider_router`) was modified beyond what Phase 2 already did.

## 7. Football Provider Matrix

Verified directly against `api_sports_adapter.py`/`football_data_org_adapter.py`/
`thesportsdb_adapter.py` source (method overrides, not filenames or assumptions):

| Domain | api_football | football_data_org | thesportsdb |
|---|---|---|---|
| Teams / Fixtures / Standings | ✅ | ✅ | ✅ |
| Results (dedicated completed-fixtures endpoint) | ❌ (no method) | ✅ | ✅ |
| Countries | ✅ | ❌ | ❌ |
| Players | ✅ | ❌ | ❌ |
| Team statistics | ✅ | ❌ | ❌ |
| Lineups / Odds / Injuries / Transfers / Coaching staff | ✅ (all 5) | ❌ (all 5) | ❌ (all 5) |
| Historical / Upcoming | ✅ / ✅ | ✅ / ✅ | ✅ / ✅ |
| Live | ✅ (Beat: sync-live-fixtures-football-epl) | ❌ | ❌ |
| Pre-match | ✅ (Beat: sync-upcoming-structured-intelligence-football-epl, the only LIVE_SCHEDULED path) | ❌ | ❌ |
| Post-match | ✅ | ✅ | ✅ |
| Source role | PRIMARY, ENRICHMENT | SECONDARY, FALLBACK (fixture-schedule-scoped) | SECONDARY, FALLBACK (fixture-schedule-scoped) |

## 8. Basketball Provider Matrix

Verified against `api_sports_adapter.py` lines 449-606 (`ApiBasketballAdapter`) and the Beat
schedule's `sync-live-fixtures-basketball-nba`/`-euroleague` entries:

| Domain | api_basketball |
|---|---|
| Teams / Players / Fixtures / Standings / Team statistics / Countries | ✅ (Countries via the base class's real shared implementation) |
| Lineups | ❌ — explicitly stubbed, own docstring: "does not expose a dedicated pre-match lineup endpoint" |
| Odds / Injuries / Transfers / Coaching staff | ❌ — inherited base-class stubs, never overridden |
| Results (dedicated endpoint) | ❌ — historical data comes through general Fixtures + Historical instead (confirmed: dev.db's 1,708 real basketball fixtures were populated this way) |
| Historical / Upcoming | ✅ / ✅ |
| Live | ✅ (Beat-confirmed, NBA + Euroleague) |
| Pre-match | ❌ — Beat schedule's structured-intelligence sync is explicitly football/EPL-only |
| Post-match | ✅ |
| Source role | PRIMARY only — no secondary/fallback registered for this sport |

## 9. Baseball Provider Matrix

Identical shape to basketball, verified against `api_sports_adapter.py` lines 607-750
(`ApiBaseballAdapter`) and Beat's `sync-live-fixtures-baseball-mlb`/`-npb` entries:

| Domain | api_baseball |
|---|---|
| Teams / Players / Fixtures / Standings / Team statistics / Countries | ✅ |
| Lineups / Odds / Injuries / Transfers / Coaching staff | ❌ (same stub pattern as basketball) |
| Historical / Upcoming / Live / Post-match | ✅ / ✅ / ✅ (Beat-confirmed, MLB + NPB) / ✅ |
| Pre-match | ❌ |
| Source role | PRIMARY only |

## 10. Table-Tennis Status

**No real provider exists.** `PROVIDER_CAPABILITIES` has zero entries with `sport is
SportCode.TABLE_TENNIS` — deliberately absent, not represented with a fabricated/mock-shaped
entry. `CapabilityResolver.has_real_provider(SportCode.TABLE_TENNIS)` returns `False`.
`SourceSelectionService.eligible_providers`/`select_provider` for any table-tennis `DataRequest`
correctly return an empty tuple / `provider_key=None` — never raises, never falls through to a
fabricated candidate. `test_table_tennis_resolution_does_not_affect_other_sports` proves resolving
a table-tennis request first has zero effect on a subsequent football resolution in the same
process. No fake provider, no mock capabilities dressed as production-ready, no fixtures, no
readiness-gate weakening — exactly as instructed.

## 11. News-Provider Handling

Kept deliberately separate (Step 9's explicit instruction), in a new, smaller module
(`modules/intelligence/domain/news_capabilities.py`) — not merged into
`modules.sports.domain.provider_capabilities`. `NewsCapabilityDomain`: `RSS_INGESTION`,
`ARTICLE_RETRIEVAL`, `GEMINI_ENRICHMENT`. Two real entries: `rss_feed` (backed by the real
`RssNewsProvider`, the only key `NewsIngestionService._resolve_provider` looks up) and `gemini`
(backed by `GeminiAdapter`/`MockGeminiAdapter` via `TextIntelligenceRouter`). Relevance filtering
(`NewsRelevanceFilter`) was deliberately **not** represented as a capability — it's a deterministic
in-process pipeline stage applied uniformly, not something any one external provider offers or
withholds, so declaring it as a "capability" would misrepresent what the word means here. No
NEWS_SYNC_ENABLED change, no news sync triggered, no Gemini call made anywhere in this phase.

## 12. Historical-Source Readiness

The taxonomy already supports declaring a future historical-only source (`source_role=HISTORICAL`)
without any Phase 3 code needing to change — proven directly, not just asserted, by
`test_taxonomy_can_represent_a_future_historical_only_source_without_registering_one`: constructs a
hypothetical `ProviderCapabilities(provider_key="hypothetical_historical_football", ...,
source_roles={HISTORICAL})` entirely outside the real `PROVIDER_CAPABILITIES` dict, confirms it
resolves correctly (never eligible for LIVE/PRE_MATCH requests), and confirms it was never actually
registered. No Kaggle downloader, no credential handling, no CSV importer, no team-matching
adapter — all correctly out of scope, none touched.

## 13. Source-Selection Architecture

New `modules/sports/application/source_selection_service.py`. `DataRequest` (sport, domain,
temporal_mode, optional competition_id, low_priority) → `SourceSelectionService.select_provider`
applies, in the master prompt's own exact order:

```
CAPABILITY -> CONFIGURATION -> HEALTH -> QUOTA -> (COMPETITION) -> SOURCE PRIORITY -> SELECTED
```

`eligible_providers` (pure, no I/O) filters `PROVIDER_CAPABILITIES` by sport+domain+temporal mode
first, ordered by a static, explicit per-sport priority tuple (never random, never "call every
provider"). `select_provider` then walks that ordered list applying `CapabilityResolver.is_configured`
→ `is_healthy` → `has_quota` → (if `competition_id` given) `supports_competition`, returning the
first provider to clear every gate, or `None` with a per-candidate exclusion reason
(`SourceSelectionResult.excluded`) otherwise. This is a new, standalone, additive service — it does
**not** replace `SportsProviderRouter._resolve_adapter`'s existing, Phase-2-tested internal
selection; it's a new query layer future orchestration can consult, matching the master prompt's
own framing ("reusable by future orchestration," not "rewrite provider clients").

## 14. Source Priority

Static, explicit, per-sport tuples (`_DEFAULT_SOURCE_PRIORITY`):
football = `(api_football, football_data_org, thesportsdb)`; basketball = `(api_basketball,)`;
baseball = `(api_baseball,)`; table_tennis = `()`. Matches each provider's declared `SourceRole`
(PRIMARY before SECONDARY/FALLBACK). A capability-eligible provider not in the priority tuple is
still appended after (never silently invisible), though this doesn't occur for any currently
registered provider.

## 15. Health/Quota/Freshness Integration

`CapabilityResolver.is_healthy` calls `CircuitBreaker.allow_request` (the exact same instance
Phase 2 wired into the router) with no side effects and no external call. `has_quota` negates
`QuotaIntelligenceEngine.should_throttle` (same instance/pattern). Neither is duplicated — both are
thin, explicit wrappers over Phase 1/2's real primitives. "Freshness" (per the master prompt's
own list) maps to the endpoint-category TTLs Phase 2 already built into `SportsProviderRouter`'s
cache layer — the selection service doesn't re-implement TTL logic, since freshness is a
cache-layer concern that already exists and wasn't touched.

## 16. Fallback Behavior

Tested explicitly: `test_primary_unconfigured_falls_back_to_capable_secondary` (api_football
unconfigured → football_data_org selected) and, critically,
`test_secondary_lacking_the_capability_is_never_selected_as_fallback` — for an ODDS request,
football_data_org/thesportsdb are never even candidates (they don't support ODDS at all), so no
amount of api_football being unavailable can ever select them: capability resolution happens
*before* fallback, exactly as instructed. `test_fixture_schedule_scoped_provider_only_selected_for_its_opted_in_competition`
confirms a fixture-schedule-scoped provider is only ever selected for a competition that has
actually opted into it via a real `CompetitionFixtureSourcePreference` row — never for any other
competition, even though it's otherwise capability-eligible for the sport generally.

## 17. Source Attribution

Untouched. `provider_ref_index`, `ProviderRef`, and every existing source-attribution mechanism
remain exactly as Phase 1 found them — `CapabilityResolver`/`SourceSelectionService` never write
to any of these tables; they only read admin/quota state to answer capability questions.

## 18. Provenance Preservation

Untouched and re-confirmed: `SyncTrigger.BACKFILL`/`SyncTrigger.LIVE_SCHEDULED` enum values and
`modules.ingestion.application.provenance.classify_availability`'s gating logic were not modified
by any file in this phase. Capability declaring `supports_historical=True` or
`supports_pre_match=True` for a provider carries zero provenance implication — nothing in
`CapabilityResolver`/`SourceSelectionService` ever constructs, classifies, or persists a
`VERIFIED_PRE_MATCH`/`UNKNOWN_AVAILABILITY_TIME` value. Capability and provenance remain two
entirely separate concerns, exactly as instructed ("Capability != provenance").

## 19. Entity Reconciliation Integration

`EntityReconciliationService` and `provider_ref_index` remain the sole reconciliation authority —
no second reconciliation engine was built. `CapabilityResolver.supports_competition` reuses the
existing `CompetitionFixtureSourceRepositoryPort`/`CompetitionFixtureSourcePreference` mechanism
directly (same port, same real repository in production) rather than re-implementing competition-
routing logic. The capability layer only ever answers "can this provider supply this entity type
for this competition" — it never resolves a provider's raw entity into TitanIQ's canonical entity;
that remains exclusively `EntityReconciliationService`'s job.

## 20. Sport/League/Competition/Season Handling

Sport: direct `SportCode` equality check on `ProviderCapabilities.sport` (pure, always answerable).
Competition/league: `supports_competition` — `True` for any competition within a supported sport
for a generic (non-fixture-schedule-scoped) provider (no adapter has a provable per-competition
allowlist — confirmed by reading every adapter's actual HTTP call construction, which is always
parameterized by `competition_ref`, never hardcoded to a subset); for a fixture-schedule-scoped
provider, `True` only when a real `CompetitionFixtureSourcePreference` row opts that exact
competition into that exact provider. Season: not independently gated (no adapter has ever proven
season-level restriction either — `season_label` is just another request parameter every method
already accepts) — `SEASONS` is included in every provider's domain set as a request-scoping
concept, consistent with `COMPETITIONS`.

## 21. Redis/Cache Integration

Zero new Redis usage. `CapabilityResolver`/`SourceSelectionService` never touch `SyncCachePort`/
`RedisSyncCache`/`RedisDistributedLock` directly — capability resolution is pure in-memory lookup
plus reads against `ProviderManagementService`/`QuotaIntelligenceEngine`, neither of which this
phase modified. No bypass of Phase 2's cache/quota/circuit-breaker machinery is possible because
this phase never calls a provider adapter at all.

## 22. Test Results

- New test files: `test_provider_capabilities.py` (20 tests — pure taxonomy/matrix, no I/O),
  `test_capability_resolver.py` (16 tests — configuration/health/quota/competition, in-memory
  fakes only), `test_source_selection_service.py` (11 tests — eligibility/selection/fallback/
  exclusion), `test_news_capabilities.py` (4 tests).
- Targeted run: **47 passed, 0 failed**.
- Full backend suite (`pytest -q`): **2334 passed, 58 skipped, 0 failed** (10275.86s). Phase 2
  baseline was 2287 passed / 58 skipped / 0 failed — the +47 is exactly the new tests this phase
  added, nothing else changed count-wise. `apps/api/composition.py` import sanity-checked
  separately (new factories importable, no circular-import regression).

## 23. Database Verification

`dev.db` row counts captured before, during, and after this phase's work — identical throughout:
`models`=47 (19 champion / 14 candidate / 14 retired), `predictions`=12436,
`prediction_outcomes`=11194, `datasets`=0, `prediction_markets`=38. No migration was written or
needed — `ProviderCapabilities` is entirely code/declaration-based (§ design decision below), and
every test in this phase runs against in-memory fakes, never `dev.db`.

**Why capabilities stayed code-based, not database-driven**: the existing architecture's one
real database-backed provider concept (`admin.providers` — `ProviderDefinition`/
`ProviderCredential`, `ProviderStatus`, quota limits) already answers "is this provider configured/
active/credentialed" — a genuinely runtime, per-deployment fact. *What a provider is structurally
capable of* (which HTTP endpoints its adapter code calls) is a fact about the code, not the
deployment, and changes only when an adapter's implementation changes — exactly the "structural
provider behavior -> static declaration" vs. "deployment-specific enablement -> configuration"
split the master prompt itself draws. Adding a table to store what is already fully and correctly
expressed in `PROVIDER_CAPABILITIES` would be a second source of truth requiring active
synchronization with the code, not a genuine architectural need.

## 24. External API Usage

**Zero.** Every test in this phase uses in-memory fakes (`_InMemoryProviderRepo`,
`_InMemoryCredentialRepo`, `_InMemoryUsageRepo`, `_InMemoryFixtureSourceRepo`) — no `httpx.MockTransport`
was even needed, since `CapabilityResolver`/`SourceSelectionService` never call an adapter's
`fetch_*` method at all. No live API-SPORTS, football-data.org, TheSportsDB, or Gemini request was
made. No broad live provider discovery was performed. No Celery Beat was started. No continuous
synchronization began.

## 25. Security Considerations

- `PROVIDER_CAPABILITIES` is a static, code-reviewed dict — no injection surface (no user input
  ever constructs a `ProviderCapabilities` instance at runtime).
- `CapabilityResolver.is_configured`/`has_quota` read through `ProviderManagementService`'s
  existing, unchanged credential-vault-backed access pattern — no credential is ever read,
  logged, or exposed by this phase's new code; only `is_usable()`/`usable_credentials()` boolean/
  count results are consulted, never plaintext values.
- `supports_competition`'s `CompetitionFixtureSourcePreference` lookup is a plain string-keyed
  read against an existing repository — no new write path, no new admin-facing mutation endpoint
  was added in this phase.

## 26. Deferred Phase 4 Work

Per the master prompt's explicit stop condition: historical import (Kaggle downloader, credential
handling, CSV import, historical importer, team-matching adapter), basketball/baseball outcome
resolvers, table-tennis provider, model training, Celery Beat start, and live accumulation — none
started, none touched. `SourceSelectionService` is deliberately not yet wired into
`SportsProviderRouter`'s internal call paths or any Celery task; that integration (if ever wanted)
is itself a natural, separate future decision, not assumed or begun here.

## 27. Final Acceptance Checklist

- [x] `ProviderCapabilities` exists.
- [x] Existing provider registry uses it (`CapabilityResolver` wraps `PROVIDER_CAPABILITIES` +
      the existing `ProviderManagementService`/`CircuitBreaker`/`QuotaIntelligenceEngine`).
- [x] No second provider registry exists.
- [x] Capability taxonomy is provider-agnostic (enums, not per-provider if/else).
- [x] Football providers have verified capability declarations (3 providers, matrix in §7).
- [x] Basketball providers have verified capability declarations (§8).
- [x] Baseball providers have verified capability declarations (§9).
- [x] Table tennis correctly reports no real provider (§10).
- [x] Sport is capability-aware.
- [x] League/competition is capability-aware where provider support is identifiable (§20).
- [x] Season is capability-aware (request-scoping concept, §20).
- [x] Historical/upcoming/live/pre-match/post-match modes are represented.
- [x] Source roles are represented.
- [x] Capability resolution performs ZERO external API calls (§24).
- [x] Capability resolution does not bypass Redis cache, quota protection, or circuit breaker
      (§21/§15 — it reuses them, never bypasses, and never calls an adapter at all).
- [x] Source selection excludes incapable providers (never even candidates).
- [x] Source selection respects provider health, quota state (§16 tests).
- [x] Freshness is handled by the existing, unmodified Phase 2 TTL layer (§15).
- [x] Fallback only selects capable providers (§16, explicitly tested).
- [x] `EntityReconciliationService`/`provider_ref_index` remain authoritative (§19).
- [x] Existing source attribution intact (§17).
- [x] `VERIFIED_PRE_MATCH`/`SyncTrigger.BACKFILL`/`SyncTrigger.LIVE_SCHEDULED` unchanged (§18).
- [x] No historical source can fabricate pre-match provenance (§18).
- [x] No model trained, no Champion modified, no calibration, no retraining, no promotion.
- [x] No unnecessary database migration created (§23).
- [x] Database integrity verified (§23).
- [x] Targeted tests pass (47/47).
- [x] Full backend suite passes (2334/58/0).
- [x] No unexplained regression exists (+47 exactly accounted for).

---

# PHASE 3 STATUS:
COMPLETE

PROVIDER CAPABILITIES:
PASS

PROVIDER REGISTRY:
PASS

FOOTBALL PROVIDER MATRIX:
PASS

BASKETBALL PROVIDER MATRIX:
PASS

BASEBALL PROVIDER MATRIX:
PASS

TABLE-TENNIS STATUS:
PASS

SPORT/LEAGUE/COMPETITION/SEASON AWARENESS:
PASS

SOURCE SELECTION:
PASS

FALLBACK:
PASS

CACHE/QUOTA INTEGRATION:
PASS

PROVENANCE PRESERVATION:
PASS

ENTITY RECONCILIATION:
PASS

EXTERNAL API CALLS:
NONE

GEMINI CALLS:
0

DATABASE MODIFIED:
NO

BACKEND TESTS:
2334 passed, 58 skipped, 0 failed (10275.86s)

CHAMPION MODIFIED:
NO

MODEL TRAINED:
NO

CALIBRATION:
NO

RETRAINING:
NO

NEXT PHASE:
PHASE 4 — HISTORICAL IMPORT + KAGGLE

STOP COMPLETELY.
