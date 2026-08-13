# TitanIQ — Milestone 2: Market → Feature → Model → Data Source → News → Community → Structured Context Mapping

**Status: analysis/design only. Nothing in this document has been implemented. No tables deleted, no models trained, no modules removed, no data fabricated.**

This document continues directly from the Milestone 1 System Audit (delivered in-session, not yet written to `docs/`). It answers, per the approved architectural direction:

1. What Tennis introduction actually requires (§2)
2. The cross-cutting architecture News Intelligence, temporal validity, structured-context features, Community Intelligence, ablation testing, versioning, production-status honesty, time-based training, and provider priority all need — these are gaps that apply *across* markets, not gaps in any one market (§1)
3. The full per-market mapping matrix for every real and proposed market (§3)
4. The specific basketball/baseball data gap to become genuinely trainable (§4)
5. A component classification appendix — reusable / needs modification / needs replacement / legacy / mock-only / structurally dead / leakage risk (§5)

## How to read the status tags used throughout

Every market row and every architecture item below is tagged with one or more of:

`REAL` `PARTIAL` `MOCK` `MISSING` `UNUSED` `INCOMPATIBLE` `REQUIRES NEW PROVIDER` `REQUIRES NEW FEATURE` `REQUIRES HISTORICAL DATA` `REQUIRES ARCHITECTURAL CHANGE` `REQUIRES FIX` (small, scoped) `LEGACY`

These map directly onto the taxonomy requested. A market can carry several tags at once (e.g. a football market can be `REAL` for sports features and `MISSING` + `REQUIRES ARCHITECTURAL CHANGE` for news features simultaneously).

---

## §1. Cross-cutting architecture — gaps that apply to every market, not any one market

These five items (temporal validity, market-specific news impact, event confidence, structured-context wiring, community intelligence, ablation testing, versioning, production-status honesty, time-based training, provider priority) are the actual blockers. Building them once unblocks every market row in §3 simultaneously — this is why they're separated out rather than repeated 40 times in a table.

### 1.1 Temporal validity / point-in-time data (Rule 5 — non-negotiable)

**Current state, confirmed in Milestone 1: this does not exist anywhere in the codebase.** `FeatureValueRepositoryPort` exposes only `get_latest()`/`list_history()` (most-recent-N) — no as-of-date parameter. `NewsEventRepositoryPort.list_for_entity()` has no cutoff parameter either. `IntelligenceRetrievalService.retrieve_all()` (called live by `PredictionEngine.generate()`) inherits this — it always returns whatever is most recent *right now*, never "as of the fixture's prediction cutoff." Training backfill scripts (`backfill_match_winner_training_data.py` and its siblings) pull feature values with no verification they reflect pre-kickoff state.

**What must be built:**

- A `prediction_cutoff: datetime` concept threaded through `PredictionContextBuilder.build()` — defaults to "now" for a live prediction, but must accept an explicit historical timestamp when building training rows.
- `FeatureValueRepositoryPort.get_as_of(entity_type, entity_id, feature_key, as_of: datetime) -> FeatureValue | None` — a new port method, additive (doesn't touch `get_latest`), backed by a `WHERE as_of <= :cutoff ORDER BY as_of DESC LIMIT 1` query. `feature_values_offline` already carries `as_of` — this is a query addition, not a schema change.
- `NewsEventRepositoryPort.list_for_entity_as_of(entity_ref, as_of: datetime, published_before: datetime) -> list[NewsEvent]` — same pattern, using `news_articles.published_at`/`news_events.detected_at`.
- New columns where "as of" isn't already captured: `effective_from`/`effective_until` on `sports.injuries`, `sports.transfers`, `sports.lineups` (an injury/lineup is valid for a *window*, not just a point — a player ruled out on Monday and returning Thursday needs `effective_until` for a Friday-fixture prediction to correctly see them as available again). `available_at` on anything sourced from a provider with sync latency (the provider *reported* something at time X, but TitanIQ didn't *have* it until sync time Y — training must use `available_at`, never `event_timestamp`, to avoid "the sync was late but we pretend we knew at kickoff" leakage).
- `DatasetBuilder.build()` must gain an explicit assertion/validation step: reject any `TrainingSample` whose underlying `feature_snapshot` cannot be proven to have existed before its fixture's kickoff. Today this is an unenforced upstream invariant (real for organically-generated predictions, unverified for backfilled ones).

**Tag:** `MISSING`, `REQUIRES ARCHITECTURAL CHANGE`. This is the single highest-priority item in this entire document — every other temporal claim in this doc (news relevance, structured-context freshness, ablation validity) depends on it existing first.

**Leakage risk this creates today (component classification G, see §5):** `backfill_correct_score_training_data.py`, `backfill_line_aware_markets_training_data.py`, `backfill_match_winner_training_data.py`, `backfill_both_teams_to_score_training_data.py` — all 14 currently-trained football Champions were bootstrapped through one of these scripts. None can currently prove their feature provenance was pre-kickoff. This doesn't mean they're wrong — football's engineered features (rolling form, expected goals) are slow-moving and the leakage window is probably small — but it is unverified, and must be re-audited once `get_as_of` exists.

### 1.2 News Intelligence pipeline — mapped stage-by-stage against the required flow

```
NEWS SOURCE → INGESTION → RAW EVENT → NLP/AI EXTRACTION → ENTITY RESOLUTION →
EVENT CONFIDENCE → TEMPORAL VALIDITY → SPORT/TEAM/PLAYER IMPACT →
MARKET-SPECIFIC IMPACT → FEATURE STORE → PREDICTION ENGINE
```

| Stage | Real component | Status |
|---|---|---|
| NEWS SOURCE | `news_sources` (3 rows: BBC Sport, ESPN Sport, ESPN NBA, all `is_official=0`) | `PARTIAL` — real table, thin roster, no official club/league sources registered |
| INGESTION | `RssNewsProvider` (real `httpx` + XML parsing) | `REAL` component, but `MISSING` scheduling — no Celery Beat entry exists; only fires on manual admin trigger |
| RAW EVENT | `news_articles` (146 rows, real) | `REAL` |
| NLP/AI EXTRACTION | `EventExtractionService` + `TextIntelligenceRouter` + real `GeminiAdapter` (credentialed, active) | Infrastructure `REAL`, but **the 50 `news_events`/49 `impact_scores` currently in the database were produced by `MockGeminiAdapter`**, not the real adapter — confirmed by DB content (templated summaries, fixed 0.5–0.7 confidence, literal `"mock_player"`/`"mock_team"` entity strings). Per Rule 4, this data **must not be treated as production intelligence.** |
| ENTITY RESOLUTION | `EntityResolutionService.find_by_alias` (real, KG alias match) | `REAL` mechanism, but currently starved — mock output isn't real UUIDs, so resolution never succeeds against the current dataset |
| EVENT CONFIDENCE | `NewsEvent.confidence` (bare float) | `MISSING` discrete taxonomy — see §1.3 |
| TEMPORAL VALIDITY | — | `MISSING` — see §1.1 |
| SPORT/TEAM/PLAYER IMPACT | `NewsImpactEngine` (real, 8-factor composite) | `PARTIAL` — computes one score, not sport/market-aware |
| MARKET-SPECIFIC IMPACT | — | `MISSING` entirely — see §1.2b |
| FEATURE STORE | `FeatureStoreEnrichmentService` (10-feature catalog, 5 wired) | `PARTIAL`/broken today — `_categorize_affected` requires UUID entity refs; mock output never parses as one, so **zero `intelligence.*` values currently exist in the offline store** despite 49 `impact_scores` upstream |
| PREDICTION ENGINE | `ConfidenceEngine` consumes `news_reliability`/`community_reliability` as one generic confidence factor | `PARTIAL` — not a per-market ML input feature, a global confidence modifier |

**Immediate, cheap fix once real extraction runs:** the UUID-parsing bug in `_categorize_affected` self-resolves the moment `EntityExtractionService` (real) produces real KG node ids instead of `MockGeminiAdapter`'s literal strings — no code change needed there, just retiring the mock as a data source (Rule 4) and scheduling real ingestion (the missing Beat entry above).

### 1.2b Market-specific News Impact model — design (replaces the single composite score)

**Required example from the approved direction:** a confirmed striker injury should weigh heavily on `both_teams_to_score`/`total_goals_over_under*`/`home_team_total_goals`, moderately on `match_winner`, and minimally-to-not-at-all on a market it has no causal relationship to.

**Proposed new entity:** `NewsMarketImpactRule`

```
sport_code
market_category            -- e.g. "goals", "clean_sheet", "match_result" — coarser than one market_key,
                            -- so one rule covers total_goals_over_under_0_5..4_5 without 5 duplicate rows
event_type                  -- INJURY, SUSPENSION, TRANSFER, MANAGER_CHANGE, LINEUP_CONFIRMED, ...
entity_role                 -- e.g. "confirmed_starter", "squad_depth", "starting_goalkeeper"
position_group (nullable)   -- STRIKER, DEFENDER, GOALKEEPER, MIDFIELDER — sport-specific
weight                      -- signed multiplier applied to the impact score before it becomes a feature
rationale                   -- free text, reviewed like a feature-registry leakage review
version, status             -- DRAFT/ACTIVE, same lifecycle discipline as FeatureDefinition
```

Worked examples to seed the initial rule set (not exhaustive — this is the *shape*, Milestone 4 populates it empirically):

| sport | event | entity | market_category | weight |
|---|---|---|---|---|
| football | INJURY (confirmed_starter, STRIKER) | attacking output | goals | high (+) |
| football | INJURY (confirmed_starter, STRIKER) | | match_result | moderate (+) |
| football | INJURY (confirmed_starter, GOALKEEPER) | | clean_sheet | high (−, opponent's clean-sheet odds rise) |
| football | INJURY (confirmed_starter, GOALKEEPER) | | match_result | moderate |
| football | INJURY (squad_depth, any) | | any | near-zero |
| football | MANAGER_CHANGE (recent, <14 days) | | match_result | low-moderate, decaying with tenure |

This finally gives the already-declared-but-dead `FeatureCategory.AI_EXTRACTED` enum value (Milestone 1 finding) a real registrant: rule-weighted news features become `AI_EXTRACTED` category feature definitions, distinct from the generic `intelligence.*`/`CONTEXTUAL` features that exist today.

**Tag:** `MISSING`, `REQUIRES NEW ARCHITECTURE` (net-new entity + registry + a scoring service; not a wiring fix).

### 1.3 Event confidence taxonomy — design

**New enum**, distinct from the existing per-*source* `TrustLevel`/`VerificationStatus` (Milestone 1 confirmed these are source-level, not event-level, and `VerificationStatus.DISPUTED` is dead code, never set):

```
NewsEventConfidenceTier: CONFIRMED | PROBABLE | UNCERTAIN | RUMOUR | CONTRADICTED | EXPIRED
```

- New column: `news_events.confidence_tier`.
- Computed by a new `EventConfidenceClassifier`, a deterministic function of: `SourceReliabilityScore.trust_level` (real, exists) + **independent-source corroboration count** (does **not** exist today — there is no article-clustering/dedup-by-event step; `content_hash` dedupes identical articles, not independent reports of the same real-world event across different sources — this needs a new clustering step, likely keyed on `(event_type, affected_entity_refs, published_at window)`) + event age relative to a per-event-type TTL (an injury status defaults to `UNCERTAIN` after N days without reconfirmation, becomes `EXPIRED` after M) + explicit contradiction detection (comparing two `NewsEvent`s about the same entity+event_type with conflicting `status` — does not exist today, needs building).
- **Consumption rule for §1.2b:** only `CONFIRMED`/`PROBABLE` events may contribute non-trivial weight in `NewsMarketImpactRule` scoring; `UNCERTAIN`/`RUMOUR` are heavily damped or zeroed depending on market risk tolerance; `CONTRADICTED`/`EXPIRED` are excluded from feature computation entirely (they may still surface in the evidence bundle for transparency, just not as ML input).

**Tag:** `MISSING`, `REQUIRES NEW ARCHITECTURE` (new column + classifier service + the corroboration-clustering step it depends on, which is itself new).

### 1.4 Structured injury/transfer/lineup → prediction features (Rule 6 — priority, cheapest real win available)

This is real, already-ingested, provider-sourced data (`sports.Injury`, `sports.Transfer`, `sports.CoachingStaffMember`, `sports.Lineup`, exposed via `sports_router.py`) that today feeds **zero** prediction features. No new provider integration required — this is pure feature engineering over tables that already exist, which makes it the fastest legitimate win in this whole roadmap, ahead of anything news/NLP-dependent.

Proposed new feature calculators, following the existing `FixtureFormDifferentialCalculator`/`RollingTeamStatAverageCalculator` pattern already in `modules/predictions`:

- **`SquadAvailabilityCalculator`** → `football.fixture.key_players_unavailable_home/away`. Needs a player-importance weighting — proposed to derive this from existing `player_statistics` (minutes-played/starts frequency over the trailing window), which is already real and ingested, rather than inventing a new signal.
- **`LineupConfirmationCalculator`** → `fixture.lineup_confirmed` (bool/confidence) + `fixture.lineup_strength_delta` (confirmed lineup's recent-output aggregate vs. full-squad rolling average — reuses `RollingTeamStatAverageCalculator`'s existing baseline rather than building a second one).
- **`ManagerTenureCalculator`** → `team.manager_tenure_days`, `team.manager_change_recent` (bool, within N days), sourced from `CoachingStaffMember.valid_from`/`valid_to` — **Milestone 3 must first confirm this entity is genuinely time-aware in practice** (the domain model supports it; whether ingestion actually populates transitions correctly wasn't specifically checked in Milestone 1).

Applies immediately, with zero data-source risk, to: `match_winner`, `both_teams_to_score`, every `total_goals_over_under*` variant, `home/away_team_total_goals`, `home/away_clean_sheet`, `home/away_win_to_nil` — i.e., most of football's real market catalog. Basketball/baseball equivalents (starting pitcher availability, rotation/injury reports) apply the same pattern once those sports have real fixtures (§4).

**Tag:** `REAL` data source, `MISSING` feature — i.e. `REQUIRES NEW FEATURE`, not `REQUIRES NEW PROVIDER`. Recommended as the first concrete build to come out of this milestone, independent of anything news/NLP-related.

### 1.5 Community Intelligence — supporting-signal architecture

- **Real today:** spam/bot filtering, credibility heuristics (`CommunityIngestionService`).
- **Missing today:** any wired provider — `build_community_ingestion_service` passes `providers={}`; `community_posts`/`community_topics` are 0 rows. Per Rule 4/§4, this stays `MISSING` — no provider is fabricated in this document.
- **Architecture requirement going forward:** volume, sentiment, consensus, contrarian-movement, spam/bot-filtered-ness, source/platform trust, and temporal relevance must be tracked as **separate** fields/features (not collapsed into one number the way `NewsImpactEngine`'s current composite does for news) — this avoids repeating the "one generic score" mistake Rule 2 explicitly rejects for news.
- **Hard cap, not just "currently zero because unwired":** once a real provider exists, `ConfidenceEngine`'s composite must structurally cap community's maximum contribution (e.g. a fixed ceiling on its weight, independent of how confident the community signal itself claims to be) — the goal is "supporting," permanently, not just "currently weak because sparse."
- Must pass through the ablation framework (§1.6) before its features are trusted in live scoring — same as news.

**Tag:** `PARTIAL` (filtering logic real) + `MISSING` (no real source) + `REQUIRES PRODUCT DECISION` (which platform — out of scope for this document to choose).

### 1.6 Ablation testing architecture

Propose extending the existing, real `BacktestService` (already WALK_FORWARD-capable) with a `feature_group` mask parameter rather than building a parallel system:

```
BASE                      -- sports-engineered features only (today's real football feature set)
BASE + STRUCTURED         -- + §1.4's injury/transfer/lineup features
BASE + NEWS               -- + §1.2b's market-weighted news features
BASE + NEWS + COMMUNITY   -- + §1.5's community features
FULL                      -- everything, including knowledge-graph-derived features
```

- New entity: `AblationRun` (market_id, feature_group_definition, log_loss, brier_score, calibration_error, sample_count, compared_against) — reuses `ChallengerEvaluationService`'s scoring math (log_loss → brier → ECE priority, `MIN_RELATIVE_IMPROVEMENT = 0.01` noise band) rather than duplicating it.
- **Decision rule, directly implementing Rule 9:** a feature group may only remain wired into a market's live `FeatureMarketMapping` if its ablation result clears the same noise band already used for Champion/Challenger comparisons. No feature is retained "because it exists."

**Tag:** `MISSING`, `REQUIRES NEW ARCHITECTURE`, but built substantially on reusable existing components (`BacktestService`, `ChallengerEvaluationService`'s comparison math) — moderate lift, not a rewrite.

### 1.7 Model/feature/dataset versioning — mandatory provenance

- **Bug fix, not a redesign:** `ModelDefinition.feature_versions` exists in the schema and is silently dropped at the only real call site (`select_and_register_challenger()` never passes it). One-call-site fix.
- **New field required:** `news_intelligence_version` — tracks which `EventExtractionService`/prompt-template version *and* which confidence-taxonomy version (§1.3) produced the news features consumed by a given prediction. Does not exist today because market-specific news features don't exist yet either (§1.2b) — build together.
- **Full provenance a production prediction must carry**, per the approved direction: `model_version` (real today), `feature_version` (real per-feature-definition, not yet per-model — the gap above), `dataset_version` (real), `prediction_timestamp` (real), `feature_snapshot`/reference (real), `news_intelligence_version` (new), `source_versions` (new — provider-level, for auditability of which adapter/API version supplied a given fact).

**Tag:** `PARTIAL` (schema exists) + `REQUIRES FIX` (population bug, one call site) + `REQUIRES NEW FIELD` (news intelligence version, depends on §1.2b/§1.3 existing first).

### 1.8 Production model status honesty (Rule 13)

Milestone 1 found 19 markets (all basketball/baseball/table_tennis) already correctly surface `NoChampionModelError` → an honest "insufficient historical data" response — **that part is already compliant** with this rule.

**The actual gap is narrower and specific:** 5 football markets — `first_half_both_teams_to_score`, `first_half_goals`, `first_half_winner`, `match_result` (deprecated), `second_half_winner` — carry a **placeholder-heuristic Champion** and are represented as ordinary `PRODUCTION` markets, indistinguishable in status from the 14 markets with a genuinely trained-and-validated Champion.

**Proposed fix:** `ModelDefinition` already has a `deployment_mode` field (confirmed present in the schema by Milestone 1). Use it to distinguish `heuristic_placeholder` from `trained_artifact`, and have market-status serialization reflect that distinction — e.g. a market whose current Champion is `heuristic_placeholder` reports `INSUFFICIENT_TRAINING_DATA` (or an equivalent honest status), not bare `PRODUCTION`, until a real trained Champion is bootstrapped for it the same way the other 14 already were.

**Tag:** `REQUIRES FIX` — well-scoped (5 markets, one status-serialization change), not urgent-scale, but explicitly non-compliant with Rule 13 today and worth doing before Milestone 3/4 trains anything new.

### 1.9 Time-based training default (Rule 14)

`AutomaticModelSelectionService.select()` defaults to `SplitStrategy.TRAIN_TEST` — a naive random shuffle — and `ScheduledRetrainingOrchestrator` never overrides it. The correct strategies (`TIME_SERIES_SPLIT`, `WALK_FORWARD`, `ROLLING_WINDOW`) already exist, are correctly implemented, and are simply never selected by the live retraining path.

**Fix, in scope for a near-term change:** flip the default and the one call site. Low code risk — the implementations are already tested.

**Not in scope for this milestone:** retraining all 14 currently-live football Champions under the corrected split (that's a Milestone 4-scale activity, and per Rule 12/§1.8's promotion discipline, a retrained Champion must still beat the existing one empirically before replacing it — this doesn't mean "retrain everything immediately," it means the *default* stops being wrong going forward).

**Tag:** `REQUIRES FIX` (default + one call site) + flagged dependency: `REQUIRES RETRAIN` for the 14 existing Champions, deferred to Milestone 4.

### 1.10 TheSportsDB / provider priority

Milestone 1 confirmed TheSportsDB is **already** correctly scoped as supplementary-only (`fixture_schedule_adapters` + `supplementary_provider_keys`, never primary, its own `preserve_existing_score` guard prevents it overwriting a primary provider's data) — this item is **mostly already compliant**, just undocumented as an explicit policy.

**Proposed, low-cost formalization:** a `ProviderPriorityPolicy` per `(sport, data_type)` — e.g. football fixtures → api-football primary, football-data.org/TheSportsDB supplementary; basketball/baseball/tennis will need the same explicit statement once real providers are selected for them (§4, §2). Recommend this be a short documentation addition (or a small registry table mirroring the existing `CompetitionFixtureSourcePreference` pattern) rather than new runtime logic — the runtime behavior it would describe already exists.

**Tag:** `MOSTLY COMPLIANT` — documentation gap, not a code gap.

---

## §2. Tennis — full introduction requirements

**Nothing tennis-related exists in the codebase today** — no plugin, no provider, no entity, no market, no data. Everything below is a requirements list, not a status report; no tennis data is fabricated anywhere in this document.

The existing `table_tennis` plugin is the closest structural template (same generic `Sport`/`Fixture`/`Player` domain model, mock-only today) — reusing its *shape*, not its content, is the fastest path, while respecting that Table Tennis itself stays untouched and legacy (Rule 11).

| Requirement | What it needs |
|---|---|
| **Sport module** | New `modules/sports/tennis/plugin.py` (mirrors `football/`, `basketball/`, `baseball/`, `table_tennis/` — `SportPluginRegistry` pattern already supports N sports, no core-architecture change needed to add a 5th... 4th-intended entry). Add `SportCode.TENNIS` to the enum (currently: `FOOTBALL, BASKETBALL, BASEBALL, TABLE_TENNIS`). |
| **Provider integration** | `REQUIRES NEW PROVIDER` — no tennis data provider is registered or credentialed anywhere. This is a product/procurement decision outside this audit's scope; the market has several category-level options (dedicated sports-data vendors, official tour feeds) but **no specific provider is selected or assumed here.** Whatever is chosen must implement `SportsDataProviderPort`, following the exact adapter pattern already proven three times (`ApiFootballAdapter`/`ApiBasketballAdapter`/`ApiBaseballAdapter` sharing `_ApiSportsHttpAdapterBase`). |
| **Fixtures/events** | Tennis's match structure is structurally different from every sport currently in the schema: **Sets → Games → Points**, best-of-3/5, no fixed time budget, no draw outcome. The current schema goes `Match → MatchEvent` with no set-level structure. **New entities required**: `Set` (set_number, games_won_p1/p2, tiebreak_score nullable), possibly `Game` if game-level granularity is wanted for in-play features later — not required for match-level markets at launch. |
| **Players** | `sports.Player` is generic and reusable as-is — individual-sport players fit the existing shape (team_id becomes optional/nullable for an individual-sport player, which the entity may already support — confirm in Milestone 3). |
| **Rankings** | `sports.Ranking` already exists as a generic entity — reusable as-is; tennis-specific concern is *which* ranking system (ATP/WTA singles/doubles) and update cadence, a provider/config detail, not a schema change. |
| **Surface** | **Does not exist anywhere today.** Hard/clay/grass materially changes player performance distributions in tennis in a way no current sport's schema models — needs a new attribute, most naturally on `Venue` (a `surface_type` field) or on a new `Tournament` concept if surface varies by event rather than by fixed venue. |
| **Historical data** | `REQUIRES HISTORICAL DATA` — zero exists. Volume/depth needed before any model is trainable is a Milestone 3 question (the same audit that will determine basketball/baseball's real gap, §4), not answerable here without fabricating an estimate. |
| **Feature sets** | New: server/returner form splits (serve-dominant sport, unlike the other three), surface-adjusted rolling form (a player's clay form isn't predictive of their grass form the way football form transfers across most fixtures), head-to-head history (more predictively load-bearing in tennis than in the team sports already built, since it's a 1v1 sport with often-repeated pairings), fatigue/schedule-density (tournament format creates back-to-back-day matches unlike scheduled weekly fixtures). |
| **Markets** | `MISSING` — proposed catalog at launch scale (mirroring basketball/baseball's 6–7 market count, not exhaustive): `tennis.match_winner` (moneyline-equivalent, no draw), `tennis.set_handicap` (spread-equivalent), `tennis.total_games` (total-equivalent), `tennis.first_set_winner` (half-equivalent), `tennis.correct_score_in_sets`, `tennis.player_total_games_won` (individual-player prop, since it's a 1v1 sport). |
| **Statistical models** | No existing statistical baseline is directly reusable — football's Poisson-family approach was already removed platform-wide (Milestone 1 finding: no Poisson predictor exists anywhere today, replaced by pure ML), so this isn't "port Dixon-Coles to tennis," it's "pick a baseline consistent with the platform's current all-ML approach" (e.g. an Elo/Glicko-style rating baseline is a common, well-understood tennis approach and slots into the existing `PredictorRegistry` pattern the same way `WeightedOrdinalPredictor` does today for `match_winner`-style markets). |
| **ML models** | Same roster already used elsewhere (`AutomaticModelSelectionService`'s 11-algorithm roster is sport-agnostic) — no new ML infrastructure needed, only tennis-specific feature sets (above) and real historical data (§ above) to train against. |
| **Training datasets** | Depends entirely on real historical data existing first — `DatasetBuilder` itself is sport-agnostic and needs no tennis-specific change. |
| **Prediction pipelines** | `PredictionEngine`/`PredictionContextBuilder`/`CalibratorPort`/`ConfidenceEngine`/`ExplainabilityEngine` are all sport-agnostic already — no new pipeline code needed, only the market/feature/provider work above. |
| **Outcome resolution** | New resolver needed — `OutcomeResolutionService`'s existing resolvers are market-shape-specific (2-way, 3-way, multiclass, threshold); tennis's `match_winner` is 2-way (no draw) so the existing 2-way resolver likely applies directly; `correct_score_in_sets` needs a new multiclass-style resolver mirroring football's `correct_score` pattern. |
| **Evaluation metrics** | Same `log_loss`/`brier_score`/calibration approach already used platform-wide — no tennis-specific metric work needed. |

**Summary tag for all of Tennis: `MISSING`, `REQUIRES NEW PROVIDER`, `REQUIRES HISTORICAL DATA`, `REQUIRES ARCHITECTURAL CHANGE` (Set-level entity is genuinely new schema, not just a wiring gap). Everything else in the stack (domain model shape, ML roster, prediction pipeline, evaluation) is real and directly reusable once those three are addressed.**

---

## §3. Market → Feature → Model → Data Source matrix

**Read this section together with §1** — structured-context, news, community, weather, and knowledge-graph *features* are `MISSING` for literally every market below today (that's §1's finding, not a per-market one). Repeating "MISSING" in five columns across ~40 rows would add rows without adding information, so each table below lists what actually differs per market — target, statistical baseline, current Champion status, sports-engineered features, data sources, and status tags — with a pointer back to the relevant §1 subsection for the shared gap.

### Football (18 real seeded markets + 1 deprecated)

*Sports features draw from confirmed real feature families: expected-goals differential (`FixtureExpectedGoalsCalculator`), rolling recent-form differentials for shots-on-target/possession/corners/fouls/cards (`FixtureFormDifferentialCalculator`), market-implied-probability + overround (`ImpliedProbabilityCalculator`/`OddsOverroundCalculator`), kickoff-timing (`HoursUntilKickoffCalculator`). Exact per-market `required_features` lists live in `market_seeding.py`'s `FeatureMarketMapping` calls — Milestone 3 should pull those verbatim for full field-level precision; this table reflects the confirmed feature *families*, not a re-derived exact list.*

| Market | Target | Champion status | Data sources | Tags |
|---|---|---|---|---|
| `match_winner` | 3-way (home/draw/away) | `REAL` — trained (logistic_regression) | api-football (primary), football-data.org/TheSportsDB (supplementary schedule/score) | `REAL` sports features; §1.4/§1.2b apply once built |
| `both_teams_to_score` | binary | `REAL` — trained (svm) | same | same |
| `total_goals_over_under` (2.5 line) + `_0_5`/`_1_5`/`_3_5`/`_4_5` variants | binary per line | `REAL` — all 5 trained (elastic_net / catboost ×3 / gaussian_nb) | same | same — one feature set, 5 target thresholds |
| `home_team_total_goals` / `away_team_total_goals` | threshold-style | `REAL` — trained (lightgbm / catboost) | same | same |
| `correct_score` | multiclass | `REAL` — trained (logistic_regression) | same | same |
| `home_clean_sheet` / `away_clean_sheet` | binary | `REAL` — trained (logistic_regression / catboost) | same | especially sensitive to §1.4's defender/GK-injury feature once built |
| `home_win_to_nil` / `away_win_to_nil` | binary | `REAL` — trained (catboost ×2) | same | same |
| `first_half_winner` / `second_half_winner` | 3-way | `PARTIAL` — **placeholder-heuristic Champion, no real training** | same | `REQUIRES FIX` per §1.8 — currently misrepresented as PRODUCTION |
| `first_half_goals` / `first_half_both_teams_to_score` | binary | `PARTIAL` — **placeholder-heuristic Champion** | same | `REQUIRES FIX` per §1.8 |
| `match_result` (deprecated) | legacy | retired, superseded by `match_winner` | — | `LEGACY` |

### Basketball (7 seeded markets, catalog-only — see §4 for the data gap)

| Market | Target | Champion status | Data sources | Tags |
|---|---|---|---|---|
| `moneyline` | binary (no draw in basketball) | `MISSING` — 0 champion | api-basketball, real fixtures **absent** (mock test data only) | `REQUIRES HISTORICAL DATA` |
| `point_spread` | threshold/handicap | `MISSING` | same | same |
| `game_total_points` | threshold | `MISSING` | same | same |
| `team_total_points` | threshold | `MISSING` | same | same |
| `first_half_winner` | binary | `MISSING` | same | same |
| `race_to_20_points` | binary/timing | `MISSING` | same | same |
| `player_points_prop` | player-level threshold | `MISSING`, additionally needs player-level real stats at volume | same | same, plus `REQUIRES NEW FEATURE` (player prop feature engineering doesn't exist for any sport yet) |

*Sports feature infrastructure that already exists and is reusable once real data lands: `RollingTeamStatAverageCalculator` already computes `basketball.team.form_points_last5` — the engineering pattern is proven, it just has nothing real to compute over yet.*

### Baseball (6 seeded markets, catalog-only — see §4)

| Market | Target | Champion status | Data sources | Tags |
|---|---|---|---|---|
| `moneyline` | binary | `MISSING` — 0 champion | api-baseball, **zero real fixtures at all** (not even mock-populated the way basketball is) | `REQUIRES HISTORICAL DATA` — the largest gap of the two |
| `run_line` | handicap | `MISSING` | same | same |
| `total_runs` | threshold | `MISSING` | same | same |
| `team_total_runs` | threshold | `MISSING` | same | same |
| `first_five_innings_winner` | binary | `MISSING` | same | same |
| `pitcher_strikeouts_prop` | player-level threshold | `MISSING` | same | same + needs starting-pitcher-specific features (workload, rest days — mentioned in the original master spec's baseball section, not built for any sport yet) |

*`RollingTeamStatAverageCalculator` already computes `baseball.team.form_runs_last5` — same story as basketball, engineering pattern proven, no real data to run it on.*

### Table Tennis (6 seeded markets) — legacy, per Rule 11

Kept for completeness of "every market," intentionally terse per the approved direction (no further investment): `match_winner`, `match_handicap`, `total_points`, `correct_score`, `race_to_11_points`, `set_winner` — all `MISSING` champion, mock-provider-only, zero real fixtures. **Tag: `LEGACY`, `MOCK`. Preserve as-is; do not expand, do not delete.**

### Tennis (proposed, 6 markets) — see §2 for full requirements

`tennis.match_winner`, `tennis.set_handicap`, `tennis.total_games`, `tennis.first_set_winner`, `tennis.correct_score_in_sets`, `tennis.player_total_games_won` — every column is `MISSING`. Listed here only to keep the "every market" requirement complete; full detail lives in §2, not repeated here.

---

## §4. Basketball & Baseball — the exact gap to become genuinely trainable

**Per the approved direction: this section identifies the gap. It does not close it, and no training happens as a result of this document.**

| Requirement | Basketball | Baseball |
|---|---|---|
| Real fixture ingestion | Provider (`api-basketball`) is registered and credentialed; sync has only ever run against mock/test data in practice | Provider (`api-baseball`) registered and credentialed; **zero real fixtures exist**, not even test-scale |
| Historical completed events | None | None |
| Team/player statistics | `TeamStatistics`/`PlayerStatistics` tables real and sport-agnostic, populated by nothing for this sport yet | Same |
| Required market outcomes | `OutcomeResolutionService` needs basketball-shaped resolvers wired for the 7 seeded markets (2-way for `moneyline`, threshold for spreads/totals) — resolvers exist generically, basketball-specific wiring unverified in Milestone 1, needs confirming in Milestone 3 | Same pattern, baseball-shaped (`run_line`, `total_runs`) |
| Feature availability | `RollingTeamStatAverageCalculator` proven and ready; no equivalent to football's `FixtureExpectedGoalsCalculator` exists for basketball (would need a possession/efficiency-based analog) | Same — no run-expectancy equivalent built yet |
| Historical feature reconstruction | Needs the temporal-validity work (§1.1) to exist *before* any historical backfill happens, to avoid repeating football's unverified-provenance pattern from the start rather than inheriting the same risk | Same |
| Dataset requirements | `DatasetBuilder` is sport-agnostic, ready once real `Prediction`/`PredictionOutcome` rows exist to build from | Same |
| Initial Champion training requirements | Once real fixtures + a full season(s) of completed results + engineered features exist, the exact same `AutomaticModelSelectionService` → `ChallengerEvaluationService` bootstrap-promotion path that produced football's 14 real Champions applies unchanged — **no new training infrastructure needed, only real data feeding the infrastructure that already exists** | Same |

**Bottom line: the blocker for both sports is data volume, not architecture.** The prediction/training/evaluation stack is sport-agnostic and already proven on football. Milestone 3 (historical data audit) is the right place to determine exactly how much real history exists/is obtainable and whether it clears a reasonable minimum-sample bar per market — this document doesn't answer that, deliberately, per the approved sequencing.

---

## §5. Component classification appendix

| Component | Classification | Note |
|---|---|---|
| `SportPluginRegistry`, `PredictionEngine`, `DatasetBuilder`, `AutomaticModelSelectionService`, `ChallengerEvaluationService`, `BacktestService`, `CalibrationFittingService`, `ConfidenceEngine` | **A. Existing, reusable as-is** | Sport-agnostic by design; Tennis and basketball/baseball-at-volume both ride these unchanged |
| `AutomaticModelSelectionService.select()` default split strategy | **B. Requires modification** | Flip `TRAIN_TEST` → `TIME_SERIES_SPLIT`/`WALK_FORWARD` default (§1.9) |
| `ModelRegistryService.register()`/`select_and_register_challenger()` (feature_versions population) | **B. Requires modification** | One-call-site fix (§1.7) |
| Market-status serialization for the 5 placeholder-heuristic football markets | **B. Requires modification** | §1.8 |
| `NewsImpactEngine` (single composite score) | **C. Requires replacement** (of its output shape, not its 8-factor computation, which stays) | Becomes an input to §1.2b's market-weighted rule engine, not the terminal score |
| `RssNewsProvider` scheduling | **B. Requires modification** | Add Celery Beat entry — component itself is fine |
| `football.match_result` market | **D. Legacy** | Already deprecated/retired in favor of `match_winner` |
| Table Tennis plugin, provider, market catalog (all of it) | **D. Legacy** | Preserve, do not expand (Rule 11) |
| `MockGeminiAdapter`-produced `news_events`/`impact_scores` (current 50/49 rows) | **E. Mock-only** | Must not be treated as production intelligence (Rule 4); real adapter exists and is credentialed |
| `MockCommunityProvider` | **E. Mock-only** | Never wired to composition.py; test-only |
| `CommunityIngestionService.providers={}` wiring | **F. Structurally dead** | Real filtering logic, zero reachable provider |
| `compute_adaptive_interval()` (quota-aware Beat scaling) | **F. Structurally dead** | Written and tested, never called from the live Beat schedule |
| `VerificationStatus.DISPUTED` | **F. Structurally dead** | Declared, never set anywhere |
| `FeatureCategory.AI_EXTRACTED`/`.COMMUNITY_INTELLIGENCE`/`.KNOWLEDGE_GRAPH`/`.LEARNED` | **F. Structurally dead** | §1.2b/§1.5 give `AI_EXTRACTED` and `.COMMUNITY_INTELLIGENCE` a real registrant going forward |
| `ExplainabilityEngine.explain_with_shap()` | **F. Structurally dead** (in the live path) | Real, tested, but only reachable from one admin diagnostic endpoint, never the per-prediction path |
| `backfill_correct_score_training_data.py`, `backfill_line_aware_markets_training_data.py`, `backfill_match_winner_training_data.py`, `backfill_both_teams_to_score_training_data.py` | **G. Data-leakage risk** | Unverified pre-kickoff feature provenance until §1.1 exists and can re-audit them |
| `feature_values_offline`/`news_events` read paths (`get_latest`/`list_for_entity`, no as-of param) | **G. Data-leakage risk** | The structural cause of the above — see §1.1 |
| Structured `Injury`/`Transfer`/`Lineup`/`CoachingStaffMember` data | **A. Existing, reusable** (as data) but currently **F. structurally dead** (as a feature input) | §1.4 — highest-priority, lowest-risk build in this document |

---

## Summary and sequencing implication (not a plan — just what this mapping makes obvious)

The gaps cluster into three tiers by cost/risk, which Milestone 3 (historical data audit) and any future implementation milestones should weigh:

1. **Cheap, safe, no new data source needed:** §1.4 (structured context features), §1.7's versioning bug fix, §1.8's status honesty fix, §1.9's split-strategy default.
2. **Moderate, builds on real existing infrastructure:** §1.2b (market-weighted news impact), §1.3 (event confidence taxonomy), §1.6 (ablation framework) — all extend components Milestone 1 confirmed are real and solid (`NewsImpactEngine`, `ChallengerEvaluationService`, `BacktestService`), none require new provider integrations.
3. **Expensive / requires a product decision outside this audit's scope:** §1.1 (temporal validity — architecturally required before 1.2b/1.3/1.6 can be trusted, so it gates the moderate tier above despite being conceptually simple), §2 (Tennis — needs a provider decision and historical data neither of which this document can supply), §1.5 (Community — needs a platform decision), §4 (basketball/baseball — needs Milestone 3's data-volume answer).

**STOP — per Rule 17.** This is the complete Milestone 2 mapping and gap analysis. Nothing has been implemented, no data fabricated, no models trained or promoted, Table Tennis untouched, no destructive changes made. Waiting for approval before Milestone 3 (Historical Data Audit — determining how much real basketball/baseball history actually exists/is obtainable, and what tennis provider/historical-data situation looks like once a provider is chosen).
