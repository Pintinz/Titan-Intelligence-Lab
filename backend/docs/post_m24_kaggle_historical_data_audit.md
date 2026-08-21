# Post-M24 Hybrid Historical Data Expansion — Kaggle + Live API Audit

**Date:** 2026-08-14
**Status:** Audit only, as instructed. No code written, no database write, no download performed.
**Boundary:** Milestone 24 is the final milestone of the TitanIQ engagement and remains unmodified.
This is a **post-M24 enhancement / data-platform audit**, not Milestone 25. No milestone report is
altered by this document.

This audit builds directly on `docs/historical_data_expansion_audit.md` (same session, immediately
prior) rather than re-deriving its findings — that report's Kaggle candidate research, dataset
schema, and 14-market gated-feature analysis are reused here and cited, not repeated in full.

---

## 1. Current TitanIQ state

Unchanged: **STATE A** (M24 final report). 0/14 genuinely-trained football markets ready. 47
`models`, 12,436 `predictions`, 71,223 `feature_values_offline`, 6,834 `fixtures`, 308 `transfers`,
68 `news_events` (0 `VERIFIED_PRE_MATCH`), 0 `datasets` persisted. Row counts re-verified identical
at the start of this audit (§25).

## 2. M24 boundary

M24 explicitly declared itself the final milestone; this document does not reopen, rename, or
reinterpret it. Every M24 safety guarantee (no Champion modification, no auto-training, no
provenance weakening) is treated as binding and unmodified here. Nothing in this audit proposes
touching a Champion, training a model, or changing `is_feature_eligible()`.

## 3. Objective

Design (not yet implement) a hybrid ingestion architecture where Kaggle-sourced historical data and
TitanIQ's existing live API/RSS/Gemini data coexist in the same normalized database, feed the same
feature-engineering and `DatasetBuilder` pipeline, and are judged by the same unmodified
`TrainingPreflightService` — with the two provenance domains (historical vs. live-verified) kept
strictly separate throughout.

## 4. Repository audit

Reused in full from the prior audit's four parallel research passes (items B–P), with corrections
noted where this audit's own direct verification found something new:

- **DatasetBuilder** (`modules/predictions/application/dataset_builder_service.py:159`) reads only
  `PredictionOutcome` + `Prediction.feature_snapshot` — never raw DB/Feature Store data directly.
  Any Kaggle-derived observation must enter training the same way every existing historical fixture
  does: as a real `Fixture` → real feature calculation → real `Prediction` → real
  `PredictionOutcome`.
- **TrainingSample** (`modules/predictions/ports/ml_model.py:47-68`): `features`, `label`,
  `reference_time`. No per-sample source/origin field — provenance lives on `DatasetLineage`.
- **Label generation**: resolver-per-market in `outcome_resolution_service.py` — 15 markets have a
  binary/three-way/grid resolver; the other 23 (of 38 total) do not (§5).
- **Dataset persistence — corrected finding**: `SqlAlchemyDatasetRepository`
  (`modules/predictions/infrastructure/persistence/repositories.py:337-373`) has been the
  *production* wiring since Milestone 20 (`apps/api/composition.py:936-943`). The prior claim (M19
  audit, repeated in M24's report) that this is "in-memory-only by design (ADR-008)" is stale — the
  gate fails today only because no code path has ever called `.upsert()`, not because persistence is
  architecturally impossible.
- **TrainingPreflightService**: 12 checks, confirmed exhaustive against source
  (`modules/predictions/application/training_preflight_service.py:93-242`). The two checks that
  actually gate all 14 trained football markets — `training_inference_feature_parity` (:187-196) and
  `required_feature_coverage_acceptable` (:198-210) — compare `FeatureMarketMapping.is_required`
  keys against `dataset.lineage.feature_keys`.
- **Provenance enums**: two independent `SyncTrigger` enums (ingestion: `SCHEDULED, MANUAL, RETRY,
  LIVE, LIVE_SCHEDULED, ADMIN_MANUAL, BACKFILL, RECONCILIATION, SYSTEM`; intelligence: `SCHEDULED,
  MANUAL, RETRY, LIVE_SCHEDULED, ADMIN_MANUAL, BACKFILL`), two independent availability-classification
  enums, both gated identically at `provenance.py:121` and `news_provenance.py:70`
  (`if trigger is not SyncTrigger.LIVE_SCHEDULED: return ... UNKNOWN_AVAILABILITY_TIME`). **`BACKFILL`
  already exists in both enums today** — this is directly relevant to §14.
- **Historical feature reconstruction** (M13–M15): `HistoricalEntityResolutionService`
  (`modules/intelligence/application/historical_entity_resolution_service.py:58`) resolves player
  team membership only via `Transfer.effective_date` chains, never `Player.team_id`.
  `HistoricalNewsRelevanceEngine` and `HistoricalFeatureReconstructionService` both require an
  explicit `historical_reference_time` and fail closed rather than fall back to current data.
- **Fixture matching** (`modules/ingestion/application/entity_reconciliation_service.py:400-453`):
  primary path is exact `(provider, external_id)`; opt-in fallback (`match_by_teams_and_date`)
  matches on internal `TeamId` UUIDs (not name strings) within a 1-day `scheduled_at` window,
  returns `None` (no match — never guesses) on 0 or >1 candidates. `preserve_existing_score` param
  already exists and controls overwrite precedence (§15).
- **Team identity**: `CrossProviderTeamMappingService`
  (`modules/ingestion/application/cross_provider_team_mapping_service.py:69-111`) is the only
  team-name-based matcher in the codebase — exact-match on NFKD-normalized, suffix-stripped names
  only (no fuzzy/edit-distance logic), binary 1.0/0.0 confidence, human-confirmed write path,
  currently hardcoded to the `football_data_org` provider name.
- **Data validation** (`modules/ingestion/application/data_validation_engine.py`): schema/required-
  field/range checks (`validate_fixture`, `validate_team`, `validate_odds`, etc.) plus batch-level
  duplicate detection (`find_duplicate_refs`). No statistical-outlier detection beyond that.
- **Odds — new finding this audit**: there is **no raw `Odds`/`FixtureOdds` table anywhere in the
  schema**, for live data either. `ProviderOddsRecord` (`modules/sports/ports/provider_gateway.py:95`)
  is a transient port-layer DTO; `FootballOddsFeatureWriter.compute_and_write()`
  (`modules/predictions/football/odds_feature_writer.py:47-60`) converts it immediately into derived
  Feature Store values (`implied_probability_home/away`, `overround`) via
  `ImpliedProbabilityCalculator`/`OddsOverroundCalculator` — raw odds are never persisted, by design,
  for any source. This is **not a schema gap**: the same writer/calculator pair can consume Kaggle's
  `OddHome`/`OddDraw`/`OddAway` columns identically (§13).
- **`CompetitionType`** (`modules/sports/domain/value_objects.py:22-25`): only three values —
  `LEAGUE`, `CUP`, `TOURNAMENT`. This is coarser than the competition-type distinction §9 asks for
  (no `CONTINENTAL`/`INTERNATIONAL`/`FRIENDLY`/`PLAYOFF`/`SUPER_CUP`) — flagged honestly, not
  silently worked around (§9, §22).

## 5. 38-market feature matrix

Confirmed via direct query: 38 total `prediction_markets` rows — 18 football (1 `deprecated`:
`football.match_result`, excluded below), 7 basketball, 6 baseball, 6 table_tennis. Presented at
market granularity (one row per market) rather than one row per individual feature, for
readability — every feature within a market shares that market's disposition unless noted.

**14 genuinely-trained football markets** — full per-feature detail already in
`historical_data_expansion_audit.md` §11; summarized here:

| Market | Historical possible? | Live possible? | Provenance required? | Kaggle potential | Final status |
|---|---|---|---|---|---|
| All 14 (correct_score, total_goals_over_under×5, home/away_team_total_goals, home/away_clean_sheet, home/away_win_to_nil, match_winner, both_teams_to_score) | Label + non-gated features: yes | Yes (already live) | Yes, on 4 (2 markets) or 10 (12 markets) of their required keys | **Zero** on gated keys; non-zero on already-passing non-gated keys | **BLOCKED**, unchanged by Kaggle |

**4 remaining football markets** (first_half_both_teams_to_score, first_half_goals,
first_half_winner, second_half_winner) — all seeded, all served live via generic
`WeightedLogistic/Linear/OrdinalPredictor` formulas (never a trained model), all require the same 4
lineup/transfer gated keys plus stat-differential features, **none has an outcome resolver** — no
market-relevant sub-match score data is ever ingested, so even non-gated coverage can never resolve
to a real `PredictionOutcome`. Kaggle's `HTHome`/`HTAway`/`HTResult` columns are half-time-only and
not mapped to any of the 14 trained markets, so they don't help here either — this dataset's
half-time columns are simply unused by this audit's recommended scope.

| Market | Historical possible? | Live possible? | Provenance required? | Kaggle potential | Final status |
|---|---|---|---|---|---|
| first_half_* / second_half_winner (4) | Features partially yes, **label: no resolver exists** | Yes (live formula) | Yes, 4 gated keys | None — no resolver means no `PredictionOutcome` ever, regardless of features | **Unresolvable by any data source until a resolver is built** — out of scope for this audit |

**19 basketball/baseball/table_tennis markets** — all seeded (production status), **zero Champions
of any kind ever seeded** (`scripts/seed_secondary_sport_markets.py` deliberately excludes them),
**zero trained ML models ever existed**, only 3 of 19 have an outcome resolver
(`basketball.moneyline`, `baseball.moneyline`, `table_tennis.match_winner` — all reuse
`_moneyline_home_win`). Required features are single-feature-family per sport
(`{sport}.team.form_*_last5` plus `{sport}.market.overround` on moneyline markets only) — none of
these 19 markets' required features are gated by `VERIFIED_PRE_MATCH` at all (no lineup/transfer/
news requirement exists for any non-football sport in this codebase today).

| Market group | Historical possible? | Live possible? | Provenance required? | Kaggle potential | Final status |
|---|---|---|---|---|---|
| Basketball (7) | Feature: yes (form_points_last5 is a plain rolling stat); Label: only moneyline has a resolver | Real `ApiBasketballAdapter` wired, but only synthetic mock fixtures exist in `dev.db` today | None — no gated features in this sport | **Out of scope** — Kaggle covers European football only, not basketball | **No Kaggle relevance; blocked on zero Champions + missing resolvers, unrelated to this audit** |
| Baseball (6) | Same shape; **zero fixtures in dev.db at all** | Real `ApiBaseballAdapter` wired, unused | None | **Out of scope** — football-only Kaggle dataset | Same as above |
| Table tennis (6) | Same shape | **No real provider adapter exists at all** — mock-only | None | **Out of scope** | Same as above |

**Summary**: of 38 total markets, Kaggle is architecturally relevant to at most 14 (the trained
football markets already covered by the prior audit), and even there, per §1 of that prior audit,
it cannot change any market's readiness. The other 24 markets are either resolver-less (4 football)
or entirely different sports Kaggle's football-only dataset cannot address (19 secondary-sport
markets) or both.

## 6. Candidate Kaggle datasets

Reused from the prior audit (§4 there) — not re-researched:

| Dataset | Publisher | License | Verdict |
|---|---|---|---|
| **Club Football Match Data (2000–2025)** | Adam Gábor | MIT | **Selected primary candidate** |
| European Soccer Database | Hugo Mathien | Non-commercial restriction, stale since 2016 | Rejected |

## 7. Licensing analysis

MIT license on the selected candidate permits commercial use (TitanIQ is a commercial product),
modification, and redistribution with attribution — the only candidate found with an unambiguous
compatible license. No authentication beyond a standard Kaggle account needed to download.

## 8. Season coverage

The primary candidate's `MatchDate` field is a genuine per-row date (not a filename-derived
season label), so season boundaries can be derived directly and reliably from real dates rather
than inferred — satisfying the master prompt's "do not rely solely on filenames" requirement by
construction. TitanIQ's own `Season.label` (VARCHAR, free-text, e.g. `"2026"`) and
`start_date`/`end_date` would need a **derivation rule**, not a schema change: a Kaggle row's
season = whichever TitanIQ `Season` row (for the resolved `Competition`) has
`start_date <= MatchDate <= end_date`. No such derivation exists in the codebase today — this is
new adapter logic, not present anywhere currently (confirmed by grep in the prior audit's Phase 1
research; no season-inference utility exists).

## 9. League coverage

The primary candidate's `Division` field (e.g. `E0`=English Premier League, `I1`=Italian Serie A,
`SP1`=La Liga, `D1`=Bundesliga, `F1`=Ligue 1) is Football-Data.co.uk's own well-documented, stable
convention — not ambiguous aliasing like "Premier League" vs "EPL" vs "English Premier League".
Mapping `Division` → TitanIQ `Competition.id` is a **small, static lookup table** (≤42 entries, one
per Kaggle-covered league), not a fuzzy-matching problem — this is meaningfully simpler than the
team-name matching problem in §11. No such lookup exists in the codebase today; it would be new,
purely-declarative adapter configuration (a Python dict or a small seed table), not a schema change.

## 10. Competition coverage

**Real gap, honestly flagged, not worked around**: `CompetitionType` has only `LEAGUE`/`CUP`/
`TOURNAMENT` — it cannot today distinguish continental competitions, international fixtures,
friendlies, playoffs, or super cups, all of which the master prompt's Phase 4 wants excluded from
league-market training data. The primary Kaggle candidate's `Division` codes are, in practice, all
domestic league divisions (Football-Data.co.uk does not cover cups/continental competitions in this
particular file) — so for *this specific candidate*, the risk of cross-competition contamination is
low by the data's own scope, not by any TitanIQ-side filtering capability. If a future candidate did
mix competition types, TitanIQ's schema could not today reliably exclude non-league fixtures beyond
the coarse `CUP`/`TOURNAMENT` split. **Per the master prompt's own Phase 7 instruction, this is
reported as an exact schema gap, not silently patched**: extending `CompetitionType` (or adding a
new field) would be a real schema change requiring its own explicit proposal and approval — not
undertaken here.

## 11. Team identity analysis

Reused and extended from the prior audit's §9 (fixture matching) finding: `CrossProviderTeamMappingService`
is the only team-name matcher that exists, and its matching strategy — NFKD-normalize, strip
"FC"/"CF"/"SC" suffixes, exact string match only, binary confidence, human-confirmed write path —
is actually a **good structural fit** for the master prompt's Phase 5 requirement ("do NOT use
uncontrolled fuzzy matching as the final authority... any ambiguous team must be marked
`ENTITY_UNRESOLVED` and excluded"). It already does exactly this (ambiguous → not written, requires
explicit confirmation). Its only limitation for this use case: it is hardcoded to the
`football_data_org` provider name (`cross_provider_team_mapping_service.py:106`). **Smallest safe
extension**: generalize the hardcoded provider string to a constructor parameter, so the identical
service (identical matching logic, identical safety properties) can run against a
`kaggle_club_football_match_data` provider namespace instead. This is a small, surgical,
behavior-preserving change to one existing class — not new matching logic, not a new architecture.
Any Kaggle team name that doesn't exact-normalized-match an existing TitanIQ team would be reported
`ENTITY_UNRESOLVED` and excluded, exactly per the master prompt's rule — never guessed.

## 12. Fixture reconciliation analysis

Reused from the prior audit's §9: the existing `match_by_teams_and_date` fallback path already
implements almost exactly the composite-identity strategy the master prompt's Phase 6 asks for
(team-pair + date proximity, ambiguous → `None`, never guessed) — it just needs (a) teams
pre-resolved via §11's extended matcher, and (b) a deterministic `ProviderRef.external_id` for
Kaggle rows to support idempotent re-import (e.g. a stable hash of
`Division|MatchDate|HomeTeam|AwayTeam`, since the Kaggle file has no native row ID). Outcomes per
the master prompt's required taxonomy:
- **MATCHED**: exact `(kaggle_provider, external_id_hash)` found on a prior import (idempotent
  rerun), or teams+date match an existing fixture within the 1-day window with exactly one candidate.
- **NEW_HISTORICAL_FIXTURE**: teams resolve, no existing TitanIQ fixture matches — a genuinely new
  historical fixture, created with `SyncTrigger.BACKFILL` (§14).
- **AMBIGUOUS**: >1 candidate in the date window — per existing `_find_fixture_by_teams_and_date`
  behavior, this already resolves to "no match" (i.e. would fall through to `NEW_HISTORICAL_FIXTURE`
  today) rather than a distinct flagged state — **a real gap**: the master prompt wants `AMBIGUOUS`
  reported and excluded, not silently treated as "create new." Reusing the existing method as-is
  would create a duplicate fixture in a genuinely ambiguous case. **This would need a small,
  explicit change**: distinguish "0 candidates → NEW" from ">1 candidates → AMBIGUOUS, exclude"
  in the Kaggle-specific caller, without touching the existing method's behavior for its current
  callers.
- **UNRESOLVED**: either team is `ENTITY_UNRESOLVED` (§11) — never reaches fixture matching at all.
- **Postponed/rescheduled fixtures**: the 1-day window already tolerates same-day time zone drift
  but would not catch a fixture postponed by more than 1 day — these would correctly land as
  `NEW_HISTORICAL_FIXTURE` (a second, distinct row) rather than falsely matching. This is the safe
  failure mode (no wrong merge), at the cost of a small number of legitimate duplicates for
  postponed matches — acceptable per the master prompt's own "do not silently guess" principle, and
  flagged here rather than hidden.

## 13. Database mapping

No new tables and no schema migration are needed for any of the data categories Kaggle's primary
candidate provides:

| Kaggle data | TitanIQ table | Notes |
|---|---|---|
| Fixture identity/date/result | `fixtures` (existing) | New rows via `BACKFILL` trigger |
| Team | `teams` (existing) | Via §11's identity resolution |
| League | `competitions` (existing) | Via §9's static Division lookup |
| Season | `seasons` (existing) | Via §8's date-range derivation |
| Shots/target/corners/fouls/cards | `team_statistics.stat_set` (JSON, existing) | Schema-flexible, no migration — same shape TitanIQ's own API-Football sync already writes |
| Odds | *(no raw table needed anywhere — §4)* | Reuse `FootballOddsFeatureWriter`/`ImpliedProbabilityCalculator` directly, feeding Kaggle's `OddHome`/`OddDraw`/`OddAway` in place of a live `ProviderOddsRecord` |
| Elo, form, clusters | *(not mapped)* | No TitanIQ equivalent; TitanIQ computes its own rolling form via `FixtureFormDifferentialCalculator`, would not consume Kaggle's pre-computed Elo/form/cluster columns |

**The one real, honestly-reported schema gap**: `CompetitionType`'s coarseness (§10). Not
addressed here — no migration proposed.

## 14. Provenance design

**No new provenance classification is needed.** `SyncTrigger.BACKFILL` already exists in both the
ingestion and intelligence enums, is already documented as one of the triggers that "must not, by
construction" ever produce `VERIFIED_PRE_MATCH" (`value_objects.py:44-57`), and is already correctly
rejected at the single enforcement choke point in both `classify_availability()`
(`provenance.py:121`) and `classify_news_availability()` (`news_provenance.py:70`) — `trigger is not
SyncTrigger.LIVE_SCHEDULED` catches `BACKFILL` identically to every other non-live trigger. A Kaggle
import tagged `SyncTrigger.BACKFILL` requires zero changes to either classification function; it
would correctly, automatically, and unavoidably classify as `UNKNOWN_AVAILABILITY_TIME` for any
structured-intelligence field (this candidate has none anyway, per §4/§12 of the prior audit) and
would never be eligible to satisfy a gated feature. Per the master prompt's own Phase 8 instruction
("If an appropriate historical source classification already exists, reuse it") — it does, so this
phase concludes with reuse, not a new-classification proposal, and does not need to STOP for
approval on a new semantic, because none is being introduced.

## 15. Historical/live separation

Source-level attribution (distinct from the *temporal* provenance in §14) is already representable
via the existing `Fixture.provider_refs: tuple[ProviderRef, ...]` field — a tuple, not a single
value, so a fixture reconciled from *both* Kaggle and API-Football can legitimately carry two
`ProviderRef` entries (`provider="kaggle_club_football_match_data"` and `provider="api_football"`)
simultaneously, satisfying the master prompt's Phase 11 "KAGGLE / API / KAGGLE+API" requirement with
zero new fields. **Precedence, using an already-existing, already-tested mechanism**:
`reconcile_fixture`'s `preserve_existing_score` parameter (`entity_reconciliation_service.py:403,
419-425`) — when set `True`, a match's existing score/data is never overwritten by a supplementary
source, only filled if absent. The explicit precedence rule this audit recommends: **a Kaggle import
always passes `preserve_existing_score=True`** — live API data, when it exists, always wins;
Kaggle only fills gaps on fixtures the live pipeline hasn't (yet) synced, or creates genuinely new
historical-only fixtures the live pipeline never covers. No new overwrite-arbitration logic needed.

## 16. Feature compatibility

Reused directly from the prior audit's §9/§10/§12 (Phase 9 gated-feature analysis): of the four
gated feature families (lineup continuity, transfer activity, and three news-impact families), the
selected Kaggle candidate supplies **zero** of them — it has no lineup, transfer, injury, or
news/article data at all. This is unchanged by expanding the audit to 38 markets, since none of the
24 additional markets add a new gated-feature dimension Kaggle could address (the 19 secondary-sport
markets have no gated features of any kind; the 4 non-trained football markets share the same 4
lineup/transfer gated keys as the trained ones).

## 17. Deduplication strategy

Per §12/§15: `ProviderRef` tuple carries multi-source attribution natively; `preserve_existing_score`
gives explicit, existing precedence (live wins); `find_duplicate_refs`
(`data_validation_engine.py:152-158`) already provides batch-level duplicate detection for a single
import run. Cross-run idempotency (re-running the same Kaggle import twice must not create a second
copy) is achieved via the deterministic `ProviderRef.external_id` hash proposed in §12 — a second
import of the same file resolves to the same external_id, hits the existing `ProviderRefIndexEntry`
exact-match lookup, and updates rather than duplicates. Every piece of this strategy reuses an
existing mechanism; none is new.

## 18. Expected additional observations

Unquantified without downloading the real file (not done — §23). The dataset page states ~475,000
total rows across 42 leagues/25 years; the fraction that would (a) match TitanIQ's existing
competition/team coverage, (b) fall within a `Season` TitanIQ already tracks, and (c) not already
exist as a live-sourced fixture is unknown until the actual CSV is inspected. This is explicitly a
Phase-7-of-the-prior-audit task (data quality audit) that has still not been performed, by design
(§23).

## 19. Expected market impact

**Zero markets move from BLOCKED to READY**, for the identical reason established in the prior
audit and reconfirmed here across all 38 markets (§5): the blocking dimension for the 14 trained
football markets is 100% gated-feature coverage, which Kaggle cannot supply at any volume; the
other 24 markets are blocked on missing resolvers or missing Champions/sport-mismatch, which Kaggle
cannot address either (it's a football-only dataset, and even for football's 4 untrained markets,
no resolver exists to consume any additional data).

## 20. TrainingPreflight impact

Not re-run against staged data, because §19 already establishes the outcome is provably unchanged
whether or not Kaggle data is imported — running it against synthetic/staged data that cannot
change the result would not produce new information. The live, unmodified `dev.db` re-run remains
**0/14 READY**, confirmed fresh in the prior audit (§15 there) and unchanged since (row counts
identical, §25).

## 21. Risks

- **Schema-gap risk (§10)**: `CompetitionType` granularity, if a future Kaggle candidate mixed
  competition types (this one largely doesn't).
- **Ambiguous-fixture risk (§12)**: the existing `_find_fixture_by_teams_and_date` treats "0 or >1
  candidates" identically as "no match" — a genuinely ambiguous multi-candidate case would silently
  create a duplicate fixture rather than being flagged `AMBIGUOUS`, unless the Kaggle-specific
  caller adds the distinction described in §12.
- **Postponed-fixture risk (§12)**: a fixture rescheduled by >1 day would land as a second, distinct
  fixture rather than matching its original — safe (no wrong merge) but not free of noise.
- **Effort-vs-benefit risk**: per §19, even a fully-executed, zero-defect Kaggle import changes zero
  markets' readiness — all engineering effort here (team/fixture resolvers, competition mapping,
  ambiguity handling) would purely expand historical box-score/odds *breadth and statistical
  robustness*, not solve the actual current blocker.
- **No risk to live pipeline integrity**: §14/§15 show the entire design reuses existing,
  already-safe primitives (`BACKFILL` trigger, `ProviderRef` tuple, `preserve_existing_score`) with
  no proposed change to `is_feature_eligible()`, `classify_availability()`, or
  `classify_news_availability()` — §22's verification confirms this by construction, not just by
  intent.

## 22. Recommended implementation

**If pursued** (contingent on §24's decision): the smallest safe implementation, per the master
prompt's own preferred architecture, is:

```
KaggleDatasetAdapter (new, reads the CSV, normalizes rows)
      ↓
HistoricalDataValidator (reuse DataValidationEngine.validate_fixture/validate_odds/validate_team_statistics — no new validation logic)
      ↓
Season/League Resolver (new, small: static Division→Competition lookup §9 + date-range season derivation §8)
      ↓
TeamIdentityResolver (extend CrossProviderTeamMappingService with a parameterized provider name — §11, one small change to one existing class)
      ↓
FixtureReconciliationService (reuse reconcile_fixture with match_by_teams_and_date=True, preserve_existing_score=True — one small addition: explicit AMBIGUOUS handling per §12)
      ↓
HistoricalDataNormalizer (reuse FixtureFormDifferentialCalculator, FixtureExpectedGoalsCalculator, FootballOddsFeatureWriter — zero new calculation logic)
      ↓
Existing TitanIQ database (fixtures, teams, competitions, seasons, team_statistics, feature_values_offline — zero new tables)
```

Every stage reuses existing, already-tested infrastructure except: one new adapter (CSV → normalized
DTOs), one new small static lookup (Division codes → Competition IDs), one parameterization of an
existing service (team matching), and one small addition to fixture matching (explicit `AMBIGUOUS`
handling). This is a genuinely small, low-risk surface — but §19 means it would not achieve the
stated goal of unblocking training.

## 23. Whether ingestion should proceed

Per the master prompt's own Phase 22 ("Kaggle is optional... if it adds little unique data... or it
cannot materially improve training readiness" → "KAGGLE INTEGRATION NOT JUSTIFIED"): **it cannot
materially improve training readiness for any of TitanIQ's 38 markets, confirmed exhaustively
(§5, §19)**. This is not a data-quality verdict (the candidate is high-quality) — it is that
training readiness was never gated on data the candidate can supply.

This audit does **not** conclude "don't do it under any circumstance" — §18/§21 identify genuine,
smaller-scope secondary value (historical box-score/odds breadth for whenever training eventually
does unblock via real time + the M24-fixed live pipeline). But per the master prompt's own
instruction not to integrate Kaggle "simply because it is available," and given this is real new
engineering surface (§22) for a benefit that is real but secondary rather than the stated primary
objective, this audit does not recommend proceeding to download/implementation without an explicit,
informed decision from you that the secondary value is worth it.

## 24. Exact next action

**Awaiting your decision, not proceeding further**:
(a) Stop here — this audit and its predecessor are the deliverable, no Kaggle data acquired, no
    code written.
(b) Proceed with acquisition + the §22 implementation anyway, for the secondary breadth/robustness
    value alone, with explicit acknowledgment it will not move any market to READY — this needs
    Kaggle credentials (not available in this environment, per the prior audit) and, per the master
    prompt's own Phase 14 instruction, should not be requested until you've confirmed this exact
    dataset is the one to proceed with.
(c) Deprioritize Kaggle entirely and focus remaining effort on the football.first_half_*/
    second_half_winner resolver gap (§5) instead — a smaller, self-contained piece of missing
    infrastructure unrelated to Kaggle, which would at least make those 4 markets' predictions
    resolvable (though still not gated-feature-eligible without real time passing).

No credentials were requested and no download was attempted, per Phase 14's explicit instruction.

## 25. Database safety confirmation

Row counts, re-verified identical to the prior audit's baseline at the time of writing this report:
`datasets`=0, `models`=47, `predictions`=12436, `feature_values_offline`=71223, `news_articles`=319,
`news_events`=68, `intelligence_sync_runs`=47, `intelligence_sync_checkpoints`=8, `transfers`=308,
`fixtures`=6834. `dev.db` was not written to at any point during this audit.

## 26. git status / git diff --stat

```
$ git status --short
 M backend/apps/worker/bootstrap.py
 M backend/modules/admin/infrastructure/celery/tasks.py
 M backend/modules/ingestion/infrastructure/celery/celery_app.py
 M backend/modules/ingestion/infrastructure/celery/tasks.py
 M backend/modules/intelligence/infrastructure/celery/tasks.py
 M backend/modules/predictions/infrastructure/celery/tasks.py
 M backend/pyproject.toml
 M backend/tests/unit/modules/ingestion/test_beat_schedule.py
 M backend/tests/unit/modules/ingestion/test_celery_tasks.py
?? backend/celerybeat-schedule*
?? backend/docs/historical_data_expansion_audit.md
?? backend/docs/milestone21_verification_report.md
?? backend/docs/milestone23_preflight_audit.md
?? backend/docs/milestone23_verification_report.md
?? backend/docs/milestone24_preimplementation_audit.md
?? backend/docs/milestone24_verification_report.md
?? backend/docs/post_m20_production_data_readiness_audit.md
?? backend/docs/post_m24_kaggle_historical_data_audit.md   <- this report
?? docs/milestone22_verification_report.md
```

All modified files listed are M24 Phase 1 (queue-routing + connection-leak fixes), already reported
and tested in `milestone24_verification_report.md` — none touched by this audit. No new file from
this audit modifies application code; only new documentation files were created.
