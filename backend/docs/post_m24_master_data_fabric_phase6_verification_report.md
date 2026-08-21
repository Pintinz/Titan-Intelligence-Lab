# POST-M24 Master Data Fabric — Phase 6 Verification Report

## Market Line & Odds Enablement

**Date:** 2026-08-15
**Scope:** Read-only architecture/provider audit of the 8 currently-blocked basketball/baseball
odds-dependent markets, followed by building the smallest correct provider-independent
market-line architecture the audit proved was actually needed — schema, resolver, persistence —
without fabricating or force-unblocking any market the evidence didn't support. No training, no
Champion creation/modification, no calibration, no Celery Beat changes.

---

## 1. Executive Summary

The audit found something more precise than Phase 5B's "no odds provider is wired": API-Basketball
and API-Baseball's real `/odds` endpoints **do exist and are reachable** with this environment's
configured credentials (confirmed via one live raw HTTP call per sport, documented in §4) — but
both calls returned **zero entries**, because every basketball/baseball fixture currently in
`dev.db` is 1-2 years old, far outside the provider's real data-retention window (independently
confirmed for baseball: "keeps a 7-day history of odds data"). No populated response was
obtainable this session without querying a current-season fixture, none of which exist in
`dev.db` yet.

Given that, this phase built the **canonical, provider-independent market-line schema and
resolver logic** (`MarketLine` entity, `market_lines` table, `MarketLineRepositoryPort` +
SQLAlchemy implementation, and `market_line_resolution_service.py`'s WIN/LOSS/PUSH/VOID/CANCELLED
resolvers) — real, tested, ready infrastructure — but deliberately did **not** write the
basketball/baseball adapters' actual bet-name-to-market-type parsing, since the exact bet-name
string a populated response would use could not be verified this session (see §4's honesty
note). Writing that parser against a guessed bet name risks the exact "structurally present but
permanently returns nothing" bug this initiative has already caught twice (Phase 5A's team-scoped
feature bug; Phase 5B's Match.started_at bug) — so it was not attempted.

All 8 markets remain classified **BLOCKED_BY_DATA** (not BLOCKED_BY_PROVIDER — the provider itself
is real and reachable; the blocker is that no populated quote exists to build/verify a parser
against, for any fixture this database currently holds). Zero training, zero Champion changes,
zero fabricated odds. One correction from Phase 5B's own report is also recorded here (§9).

---

## 2. Step 1 — Read-Only Architecture Audit

Searched `backend/` for every term the phase's checklist named
(`MatchOdds`/`Odds`/`MarketOdds`/`MarketLine`/`BettingMarket`/`PredictionMarket`/`OverUnder`/
`Spread`/`Moneyline`/`ProviderOdds`/`bookmaker`/`sportsbook`/`implied probability`/`overround`).
Found real, pre-existing infrastructure, not absent as Phase 5B's schema-table search alone
might have suggested:

- **`ProviderOddsRecord`** (`modules/sports/ports/provider_gateway.py`) — a real, working DTO:
  `fixture_ref`, `home_win`, `draw`, `away_win` (decimal odds). Moneyline-only, no `line`/`bookmaker`/
  `timestamp` field.
- **`ApiFootballAdapter.fetch_odds`** — a real, working implementation calling `/odds?fixture={id}`,
  parsing `response[].bookmakers[].bets[]`, filtering `bet.name == "Match Winner"`, taking the
  first bookmaker. This is football's own, already-shipped, already-tested pipeline.
- **`FootballOddsFeatureWriter`** (`modules/predictions/football/odds_feature_writer.py`) — feeds
  `ImpliedProbabilityCalculator`/`OddsOverroundCalculator` from a `ProviderOddsRecord`, writing
  three derived features (`implied_probability_home/away`, `overround`) to the Feature Store.
  Never persists the raw odds record itself — a **derived-feature-only pipeline**, not a raw
  market-line store. This is the reason Phase 5B's schema search (`grep` for `odds`/`market_line`
  table names) correctly found nothing: football's own pipeline was never designed to persist a
  raw line, only to compute and discard.
- **`SqlAlchemyMarketLineRepository` and `market_lines` table did not exist before this phase** —
  confirmed by the same grep; this is the genuine, real gap this phase filled.
- **`SportsProviderRouter.fetch_odds(sport_code, fixture_ref, now, low_priority=True)`**
  (`modules/sports/infrastructure/providers/provider_router.py`) — already fully sport-agnostic
  and already cache/quota/circuit-breaker-wrapped, with cache key
  `("odds", sport_code, fixture_ref.provider, fixture_ref.external_id)`. **This is the single most
  important audit finding**: the entire request-routing/cache/quota layer for odds already
  supports every sport, including basketball and baseball, with zero code changes needed. It
  simply calls whichever adapter is registered for that `sport_code`.

## 3. Step 2 — Provider Capability Audit (Evidence Matrix)

| Provider | Historical | Upcoming | Moneyline | Spread | Total | Team Total | Evidence |
|---|---|---|---|---|---|---|---|
| `api_football` | Yes | Yes | Yes | No | No | No | `ApiFootballAdapter.fetch_odds`, real, shipped, feeds `FootballOddsFeatureWriter`. |
| `api_basketball` | **No (retention window)** | **Reachable, unverified data** | Provider real, TitanIQ adapter unimplemented | same | same | same | Live raw `/odds` call this phase (§4): 200 OK, 0 entries, for a June-2024 fixture. Real `/odds`, `/bookmakers`, `/bets` endpoints confirmed via public API-Sports documentation search (season/bet/bookmaker/game/league filters). |
| `api_baseball` | **No (7-day retention, documented)** | **Reachable, unverified data** | Provider real, TitanIQ adapter unimplemented | same | same | same | Live raw `/odds` call this phase (§4): 200 OK, 0 entries, for a November-2023 fixture. Public documentation confirms `/odds`, `/odds/bets`, `/odds/bookmakers`, 7-day retention. |
| `football_data_org` | No | No | No | No | No | No | `FootballDataOrgAdapter.fetch_odds` is an explicit stub returning `None` — "Odds stay api-football's job by design." Football-only provider regardless. |
| `thesportsdb` | No | No | No | No | No | No | `TheSportsDbAdapter.fetch_odds` is an explicit stub — same reasoning, same football-only scope. |

Neither `football_data_org` nor `thesportsdb` cover basketball/baseball fixtures at all in this
codebase's registered scope — confirmed by their adapters' `fetch_teams`/`fetch_fixtures` methods
and `SportsProviderRouter`'s `real_adapters` wiring (`composition.py:546-548`: `football`→
`ApiFootballAdapter`, `basketball`→`ApiBasketballAdapter`, `baseball`→`ApiBaseballAdapter` —
`football_data_org`/`thesportsdb` are registered as football-only supplementary sources
elsewhere, never as basketball/baseball adapters).

---

## 4. Live Verification — What Was Actually Called, and Why

Per the phase's own free-tier rule ("make the smallest possible request; document exact call
count"), exactly **one real HTTP call per sport** was made — `_get("/odds", {"game": external_id})`
against `v1.basketball.api-sports.io` and `v1.baseball.api-sports.io`, using this environment's
real, already-configured `api_basketball`/`api_baseball` credentials (confirmed present in
`providers`/`provider_credentials` before calling — never printed or logged) and the most recent
fixture each sport actually has in `dev.db`:

- **Basketball**: fixture scheduled 2024-06-18, external_id `400924`. Result: HTTP 200, `response: []`
  (0 entries). No `errors` field, no auth failure — the request was genuinely accepted and
  answered, just with nothing to return.
- **Baseball**: fixture scheduled 2023-11-05, external_id `151815`. Result: HTTP 200, `response: []`.
  Same shape.

**Total external API calls this phase: 2** (one per sport, both against `/odds`, both read-only,
neither retried). **Gemini calls this phase: 0.**

**Why the adapter parser was not written despite the endpoint being real**: `ApiFootballAdapter
.fetch_odds` filters on `bet.get("name") == "Match Winner"` — a string verified against football's
real response at the time that adapter was built. Public documentation confirms API-Basketball/
API-Baseball share the same `bookmakers[].bets[].values[]` structural shape, but not the exact bet
name a populated basketball/baseball moneyline market uses (a plausible convention is
"Home/Away," but this was not confirmed against a real populated response — every fixture `dev.db`
holds is outside the provider's retention window, and fabricating a synthetic fixture id purely to
probe further would not produce genuine data either). Writing a parser against an unverified
string would either (a) silently match nothing forever if wrong — the exact "present but
structurally useless" defect class this initiative has already found and fixed twice — or (b)
risk misclassifying a real bookmaker line under the wrong market type. Per the ABSOLUTE DATA
INTEGRITY RULE ("if the source does not provide a value: NULL/unavailable... do not substitute...
a calculated estimate"), leaving this unresolved and documented is the correct outcome, not a
guess.

---

## 5. Step 3 — Odds Data Model Audit

Confirmed no existing structure could represent a variable, per-fixture bookmaker line:
`ProviderOddsRecord` is moneyline-only with no `line`/`bookmaker`/`timestamp`; football's own
markets never needed one because their over/under lines are **fixed by market definition**
(`football.total_goals_over_under_2_5` bakes the 2.5 threshold into the market itself, resolved
directly from the final score — no bookmaker line is ever read for it). Basketball/baseball's
spread/total/team-total markets are the different, classic sportsbook shape where the line itself
varies per fixture and must be fetched — a genuine, new requirement, not an oversight.

**No duplicate structure was created.** `Fixture.period_scores` already serves the period-score
role and was not touched. No `ApiBasketballOdds`/`ApiBaseballOdds`/`KaggleOdds` provider-specific
table was created — provider-specific parsing stays behind the adapter boundary per the phase's
explicit rule (§6).

---

## 6. Step 4 — Market-Line Canonical Model (Built This Phase)

`MarketLine` (`modules/sports/domain/entities.py`) — provider-independent, one row per real
observed quote:

```python
@dataclass(frozen=True)
class MarketLine:
    id: MarketLineId
    fixture_id: FixtureId
    sport_code: str
    provider: str
    bookmaker: str
    market_type: MarketLineType      # MONEYLINE | SPREAD | TOTAL | TEAM_TOTAL
    selection: str                   # HOME | AWAY | DRAW | OVER | UNDER
    line: float | None               # None for MONEYLINE
    price: float
    fetched_at: datetime
    observed_at: datetime | None     # the bookmaker's own quote time, when genuinely supplied
    team_side: str | None            # HOME | AWAY — required only for TEAM_TOTAL
    version: int = 1
```

`ProviderMarketLineRecord` (`modules/sports/ports/provider_gateway.py`) is the matching port-layer
DTO a future adapter method (`fetch_market_lines`) would return — same field shape, so
reconciliation is a straight copy with no provider-specific logic crossing into the domain layer.
`ProviderOddsRecord` (football's own DTO) was **not modified or replaced** — a deliberate,
explicit decision, since football's pipeline is already working and the master prompt cautions
against rewriting it unnecessarily.

`market_lines` table (`MarketLineModel`) — append-only (every `record()` call inserts a new row,
never updates in place), so a line's real movement over time is preserved rather than lost to an
upsert. Applied to `dev.db` this phase via an additive, empty `CREATE TABLE` (§10) — no other
table was touched.

---

## 7. Step 5 — Timestamp and Temporal Integrity

`MarketLine.observed_at` is `None` unless the provider genuinely supplies a quote timestamp — never
backfilled from `fetched_at`. `MarketLineRepositoryPort.get_latest_for_fixture(fixture_id,
market_type, before=...)` is the enforcement point: passing a real `before` cutoff (the fixture's
kickoff, for a pre-match feature) excludes any line fetched at or after that point — proven by a
real test (`test_get_latest_for_fixture_respects_the_before_temporal_gate`, §12) that records a
post-cutoff quote and confirms it is invisible to a caller passing the earlier cutoff. This is the
same "point-in-time correctness" discipline the existing Feature Store retrieval path already
enforces elsewhere in the codebase — reused in spirit, not duplicated in code (no shared class
was warranted for a single comparison).

---

## 8. Steps 6-7 — Historical and Upcoming Odds

**Historical**: not available from `api_basketball`/`api_baseball` for anything currently in
`dev.db` (§4). No Kaggle or other historical odds dataset was evaluated this phase — the master
prompt's own instruction not to download a dataset merely to satisfy the phase, combined with
Phase 4's already-established finding that no Kaggle credentials are configured in this
environment, made that avenue moot without new authorization.

**Upcoming**: the provider endpoint is real and reachable (§4), but TitanIQ does not yet ingest
any *current* basketball/baseball fixture (`dev.db`'s newest basketball fixture is from June
2024) — there is nothing "upcoming" to query odds for yet, independent of the odds question
itself. This is a fixture-ingestion gap, not an odds gap, and out of this phase's scope.

**Classification: BLOCKED_BY_DATA** for both — not BLOCKED_BY_PROVIDER (the provider genuinely
supports this), not BLOCKED_BY_ARCHITECTURE (the canonical schema now exists and is ready).

---

## 9. Correction to Phase 5B's Own Report

While capturing this phase's DB-safety snapshot, the actual `prediction_markets` row count was
found to be 38, not the 43 Phase 5B's report and final response claimed — the five new basketball
period-winner markets were implemented and tested in Phase 5B, but
`scripts/seed_secondary_sport_markets.py` was never re-run against `dev.db` before that phase's
report was written. Caught and corrected immediately this phase (§10): the script was run,
confirmed idempotent (the pre-existing 7 basketball/6 baseball/6 table_tennis markets were
untouched), bringing the count to the real 43 that report always claimed. No Champion, prediction,
or outcome row was affected by running it. Phase 5B's own report has been amended with this note.

---

## 10. Database Safety — Before/After Delta

| Table | Before Phase 6 | After Phase 6 | Delta | Explanation |
|---|---|---|---|---|
| `prediction_markets` | 38 | 43 | **+5** | Phase 5B's own markets, actually seeded this phase (§9) — not new Phase 6 work. |
| `market_lines` (new table) | n/a | 0 | **+1 table, 0 rows** | The new canonical schema, additive, empty — no real market-line data exists to persist. |
| `feature_definitions` | 47 | 47 | 0 | No new feature was created. |
| `feature_values_offline` | 72,744 | 72,744 | 0 | Unchanged. |
| `fixtures` / `teams` / `competitions` / `seasons` / `matches` | 6,834 / 215 / 7 / 18 / 178 | same | 0 | Unchanged. |
| `prediction_outcomes` | 11,194 | 11,194 | 0 | Unchanged — no market lines exist to resolve. |
| `predictions` | 12,436 | 12,436 | 0 | Unchanged — no training/generation was performed. |
| `models` (Champion) | 19 | 19 | 0 | **No Champion was created, modified, or promoted.** |
| `models` (candidate/retired) | 14 / 14 | 14 / 14 | 0 | Unchanged. |
| `calibration_reports` | 0 | 0 | 0 | Unchanged — no calibration was run. |
| `provider_ref_index` / `news_articles` / `news_events` / `intelligence_sync_runs` / `sync_checkpoints` | unchanged | unchanged | 0 | Unchanged — no new provider syncs were run beyond the two read-only `/odds` calls. |
| `players` / `player_statistics` | 100 / 0 | 100 / 0 | 0 | Unchanged. |

**Schema changes**: one new table (`market_lines`), applied additively via
`Base.metadata.create_all(tables=[MarketLineModel.__table__])` — no existing table's columns
were altered. `DATABASE MODIFIED: YES` (the +5 markets and the new empty table), but every
Champion-adjacent and training-adjacent table is unchanged.

---

## 11. Testing

**28 new tests, all passing:**

- `tests/unit/modules/predictions/test_market_line_resolution_service.py` (22 tests) — moneyline
  WIN/LOSS/UNKNOWN-on-tie; spread WIN/LOSS/PUSH (favorite covers, favorite fails, underdog covers,
  exact-line PUSH); total OVER/UNDER WIN/LOSS/PUSH; `resolve_market_line`'s dispatch for all four
  market types including TEAM_TOTAL's home/away `team_side`; CANCELLED voids the line;
  POSTPONED returns VOID; a fixture not yet COMPLETED (LIVE/SCHEDULED) is UNKNOWN, never guessed;
  a SPREAD/TOTAL with `line=None` is UNKNOWN, never resolved as if a real line existed; a
  TEAM_TOTAL with no `team_side` is UNKNOWN, never guessed which team it was quoted for.
- `tests/unit/modules/sports/test_market_line_repository.py` (6 tests) — record/list round-trip;
  append-only (a second quote does not overwrite the first); `get_latest_for_fixture` returns the
  most recent; the `before` temporal gate genuinely hides a post-cutoff quote; returns `None` when
  nothing is recorded; `list_for_fixture` never leaks another fixture's lines (sport/fixture
  isolation).

Targeted run: **164 passed, 0 failed** (the two new files plus the market-seeding, market-catalog,
and outcome-resolution files these changes touch or are adjacent to).

Full backend suite: see §14.

---

## 12. Market Resolution — Push/Void/Cancelled Handling

Explicitly implemented and tested (§11), per the phase's own requirement:

- **WIN/LOSS**: standard sportsbook conventions — spread uses the selected side's own margin plus
  its own line; totals compare the actual total against the line.
- **PUSH**: exact equality against a whole-number line — never silently classified as WIN or LOSS.
- **VOID**: a POSTPONED fixture.
- **CANCELLED**: a CANCELLED fixture.
- **UNKNOWN**: a fixture not yet COMPLETED, a missing `line` value, a missing `team_side` for
  TEAM_TOTAL, or a genuine moneyline tie (an unmodeled scenario for these sports) — never guessed.

No bookmaker-specific logic is embedded — `resolve_market_line` operates purely on the canonical
`MarketLine` entity and a fixture's actual score/status, identical regardless of which provider or
bookmaker originally supplied the quote.

---

## 13. Basketball / Baseball Market Results

| Market | Classification | Reason |
|---|---|---|
| `basketball.moneyline` | BLOCKED_BY_DATA | Provider endpoint real/reachable; zero populated data available to verify a parser against for any fixture this DB holds. |
| `basketball.point_spread` | BLOCKED_BY_DATA | Same — additionally needs the SPREAD resolver's real line, now built and tested but unfed. |
| `basketball.game_total_points` | BLOCKED_BY_DATA | Same, TOTAL resolver built and tested, unfed. |
| `basketball.team_total_points` | BLOCKED_BY_DATA | Same, TEAM_TOTAL resolver built and tested, unfed. |
| `baseball.moneyline` | BLOCKED_BY_DATA | Same reasoning as basketball; baseball's shorter (7-day) retention window makes this even less reachable for any but a live current fixture. |
| `baseball.run_line` | BLOCKED_BY_DATA | SPREAD resolver applies identically; unfed. |
| `baseball.total_runs` | BLOCKED_BY_DATA | TOTAL resolver applies identically; unfed. |
| `baseball.team_total_runs` | BLOCKED_BY_DATA | TEAM_TOTAL resolver applies identically; unfed. |
| Basketball period-line variants (`q1_total`…`q4_total`, `first_half_total`, `second_half_total`) | BLOCKED_BY_DATA | Evaluated per the phase's own invitation; same missing-line reasoning, no new work attempted beyond documenting it. |
| Baseball `first_five_innings_total`/`first_five_team_total` | BLOCKED_BY_DATA | Same. |

**`basketball.race_to_20_points`**: status unchanged from Phase 5B (BLOCKED_BY_DATA — no
play-by-play granularity). Not re-evaluated through odds infrastructure, per this phase's own
explicit instruction not to.

**Player props** (`basketball.player_points_prop`, `baseball.pitcher_strikeouts_prop`): not
touched this phase, per explicit instruction — remain BLOCKED_BY_ARCHITECTURE per Phase 5B's
finding (no player-statistics ingestion pipeline exists for any sport).

---

## 14. Full Regression Suite Result

**2,415 passed, 58 skipped, 0 failed** (600.07s / 10:00). Baseline entering this phase (after the
Phase 5B seeding correction, §9) was 2,387 passed / 58 skipped / 0 failed — a delta of **+28
passed, 0 skipped change, 0 failed**, exactly matching this phase's 28 new tests (22 resolver +
6 repository). Zero regressions.

---

## 15. Remaining Blockers and Recommended Next Phase

**Remaining blocker (single root cause for all 8 markets)**: no populated `/odds` response has
ever been observed for basketball or baseball in this environment, because every fixture
currently ingested is outside the provider's retention window. This is fundamentally a
**fixture-recency gap**, not an odds-architecture gap — the schema, resolver, and cache/quota
routing are all real and ready (§6, §11, §2's router finding).

**Recommended next phase**: ingest at least one current-season basketball and baseball fixture
(reusing the already-existing, already-generic fixture sync path), then make one additional
verification `/odds` call against it to observe a real populated response and confirm the exact
bet-name convention — at that point, `ApiBasketballAdapter.fetch_market_lines`/
`ApiBaseballAdapter.fetch_market_lines` can be written against genuine evidence rather than
documentation alone, and the already-built `MarketLine`/`market_line_resolution_service.py`
pipeline can be wired end-to-end without further architecture work. A separate Player Statistics
Ingestion phase remains the path for the two player-prop markets, unchanged from Phase 5B's
recommendation.

---

**STOP COMPLETELY. DO NOT PROCEED TO THE NEXT PHASE WITHOUT EXPLICIT AUTHORIZATION.**
