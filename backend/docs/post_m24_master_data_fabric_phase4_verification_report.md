# POST-M24 Master Data Fabric — Phase 4: Historical Import + Kaggle Integration

**Verification Report**

Status at time of writing: implementation, tests, and targeted regression complete; full backend
regression suite launched and running in the background (previous baseline: 2334 passed / 58
skipped / 0 failed). This report will be finalized with the exact suite result once it completes.

---

## 1. Executive Summary

Phase 4 builds a provider-agnostic historical-import subsystem — `HistoricalImportService` plus a
`HistoricalSourcePort` abstraction (Kaggle-shaped CSV as one concrete implementation) — that
reconciles historical fixture/team/competition/season data through the *existing*,
already-tested `EntityReconciliationService`, with zero new matching engines, zero schema
migrations, and zero changes to provenance, calibration, training, or Champion-model machinery.

**No real Kaggle dataset was downloaded or imported in this session.** This environment has no
Kaggle API credentials configured (`KAGGLE_USERNAME`/`KAGGLE_KEY` unset, no `~/.kaggle/kaggle.json`
present — checked directly, not assumed). Per the master prompt's own credential-safety rule, the
download portion is documented as blocked rather than fabricated, bypassed, or scraped around. What
*was* built, tested, and verified against real code paths is the full DRY_RUN → VALIDATE → IMPORT
pipeline, exercised end-to-end against representative CSV fixtures shaped exactly like the real
candidate datasets researched below (see §5–§8) — proven correct and safe, ready to run against a
real downloaded file the moment credentials are supplied by an operator.

---

## 2. Scope & Authorization

Authorized by the Phase 4 master prompt following Phase 3's completed report (baseline: 2334
passed / 58 skipped / 0 failed, all Phase 1–3 acceptance criteria PASS). Scope: build the
historical-import abstraction, research real Kaggle dataset candidates per sport, reconcile
historical data through existing entity-resolution machinery, enforce strict provenance separation
(`SyncTrigger.BACKFILL`, never `VERIFIED_PRE_MATCH`), prevent leakage, preserve existing
higher-authority live data, and support DRY_RUN/VALIDATE/IMPORT modes. Training, calibration,
Champion promotion, and unattended Celery Beat are explicitly out of scope and were not touched.

---

## 3. Step 1 — Repository Audit Findings

Read directly from source (not assumed) before any code was written:

- **`EntityReconciliationService`** (`modules/ingestion/application/entity_reconciliation_service.py`)
  is the sole reconciliation authority in the codebase — one method per entity kind
  (`reconcile_team`, `reconcile_competition`, `reconcile_season`, `reconcile_fixture`, …), each
  resolving identity via `provider_ref_index` first. `reconcile_fixture` already supports
  `match_by_teams_and_date=True` (cross-provider convergence, added for the football-data.org
  integration) and `preserve_existing_score=True` (a supplementary source's score never overwrites
  an existing authoritative one) — **both flags Phase 4 reuses verbatim**, unchanged.
- **`provider_ref_index`** (`ProviderRefIndexRepositoryPort`) is a generic `(provider, external_id,
  entity_kind) -> internal_entity_id` index, already provider-agnostic by construction — a
  historical source is just another `provider` string to it. No schema change needed.
- **`CrossProviderTeamMappingService`** (`modules/ingestion/application/
  cross_provider_team_mapping_service.py`) already implements exact-normalized-name team matching
  (`_normalize_name`: lowercases, strips diacritics, strips club-suffix noise like "FC"/"CF") with
  a pure `suggest_mappings` read path and a `confirm_mappings` write path. Its write path is
  hardcoded to the `football_data_org` provider key, so Phase 4 reuses only the pure
  `_normalize_name` function (imported directly, not duplicated) at the read layer, and writes its
  own `provider_ref_index` rows through the same `ProviderRefIndexEntry` shape.
- **`Fixture`/`Team`/`Competition`/`Season`** domain entities (`modules/sports/domain/entities.py`)
  and their `ProviderFixtureRecord`/`ProviderTeamRecord` pre-resolution DTOs
  (`modules/sports/ports/provider_gateway.py`) already assume raw provider identity strings, not
  yet-resolved internal ids — the exact shape a historical CSV row naturally produces.
- **`Dataset`/`DatasetBuilder`/`DatasetRepositoryPort`/`SqlAlchemyDatasetRepository`**
  (`modules/predictions/domain/dataset.py`, `application/dataset_builder_service.py`) build
  training samples exclusively from real `Prediction.feature_snapshot` output — never from raw
  historical rows directly (ADR-052: "no algorithm may bypass the Feature Store"). This confirms
  historical import's job correctly ends at fixture/team/score reconciliation: it never writes a
  feature, so it structurally cannot leak into `DatasetBuilder`. **Left completely untouched.**
- **`SyncTrigger`** (`modules/ingestion/domain/value_objects.py`) already has `BACKFILL` — "a
  one-off dev/ops script backfilling historical data long after the fact" — added in a prior
  milestone specifically for this purpose. No enum change needed.
- **`classify_availability`/`VERIFIED_PRE_MATCH`** (`modules/ingestion/application/provenance.py`)
  is scoped specifically to `Lineup`/`Injury`/`Transfer`/`Suspension` reconciliation — base
  `Fixture`/`Team` reconciliation (which is all historical import ever touches) carries no
  availability classification at all. There is structurally no gate to bypass here.
- **`SyncRun`/`SyncRunRepositoryPort`** (`domain/entities.py`, already used by every real sync path)
  is what Phase 4 uses to record each IMPORT-mode run, tagged `trigger=SyncTrigger.BACKFILL`.
- Existing backfill scripts (`backend/scripts/backfill_*.py`) all follow the same
  `composition.build_*` + `async_sessionmaker(get_engine())` pattern — Phase 4's own
  `build_historical_import_service` factory follows it identically for consistency, though no
  standalone script was written this phase (no real file to run one against yet).

**No importer existed anywhere in the codebase prior to this phase** (confirmed by grep — no
`Kaggle`, `Historical*`, or CSV-ingestion references anywhere under `modules/` before this phase's
changes).

---

## 4. Step 2 — Database Safety Baseline

Captured directly from `dev.db` before any Phase 4 write (read-only `SELECT COUNT(*)` per table):

| Table | Row count |
|---|---|
| fixtures | 6,834 |
| teams | 215 |
| competitions | 7 |
| seasons | 18 |
| prediction_outcomes | 11,194 |
| feature_values_offline | 71,223 |
| datasets | 0 |
| models | 47 |
| predictions | 12,436 |
| news_articles | 319 |
| news_events | 68 |
| provider_ref_index | 7,529 |
| sync_checkpoints | 201 |
| intelligence_sync_runs | 47 |
| leagues | *no such table — this codebase names the concept `competitions`, confirmed, not a gap* |
| alembic_version | *no such table — this dev.db's schema is applied directly, not Alembic-tracked; consistent with every prior phase's own DB verification in this session* |

Matches exactly the Phase 2/Phase 3 baseline already on record (`models=47`, `predictions=12436`,
`prediction_outcomes=11194`) — zero drift since Phase 3, and **zero Phase 4 writes have touched
`dev.db`**: every test in this phase ran against an isolated in-memory SQLite database (the same
pattern `test_entity_reconciliation_service.py` already uses), never against `dev.db` itself. This
baseline remains the live starting point for a future session that runs a real IMPORT.

---

## 5. Step 3–4 — Kaggle Dataset Research: Football

Researched live via the Kaggle site itself (rendered through a real browser session, not guessed
from training knowledge — Kaggle's dataset pages are JS-rendered and a plain fetch only returns the
page title, so this required actually loading the page).

**Candidate: "International football results from 1872 to 2026"** (Kaggle:
`martj42/international-football-results-from-1872-to-2017`)
- **Owner**: Mart Jürisoo
- **License**: **CC0: Public Domain** (confirmed on the dataset's own License panel — the strongest
  possible license for reuse, no attribution or share-alike obligation)
- **Row count**: 49,393 match results (`results.csv`), plus `goalscorers.csv`, `shootouts.csv`,
  `former_names.csv`
- **Coverage**: men's full international matches only (national teams — FIFA World Cup, continental
  championships, and friendlies), 1872–2025. Explicitly **excludes club football**, Olympic
  matches, and B-team/U23/league-select matches.
- **Columns**: `date, home_team, away_team, home_score, away_score, tournament, city, country,
  neutral` — a clean, direct match for `HistoricalFixtureRecord`'s shape.
- **Limitation, documented honestly**: TitanIQ's real live providers (api-football,
  football-data.org, TheSportsDB) are scoped to **club competitions** (EPL, etc. — confirmed in the
  Phase 3 capability audit). This dataset is international-team football, so its real-world overlap
  with TitanIQ's existing 215 teams / 7 competitions is expected to be small — most rows would
  create new national-team entities under a `historical:` provider namespace rather than converging
  onto existing club fixtures. It remains a legitimate, high-quality, zero-risk-license candidate
  for enriching TitanIQ's cross-provider knowledge graph with international results, but it is
  **not** the dataset to reach for if the goal is enriching existing club-competition history.

**Candidate: "Club Football Match Data (2000 - 2025)"** (Kaggle:
`adamgbor/club-football-match-data-2000-2025`) — verified live in this session, on request.
- **Owner**: Adam Gábor
- **License**: **MIT** (confirmed on the dataset's own License panel). Note: MIT is the uploader's
  own license grant on the compiled CSV; the underlying raw data is itself sourced from
  Football-Data.co.uk (match results/statistics) and ClubElo (Elo ratings) per the dataset's own
  "Match results and statistics provided in the table are taken from Football-Data.co.uk" credit.
  MIT covers this specific compiled artifact — a future real-import session should still spend one
  minute confirming Football-Data.co.uk's own terms are compatible with TitanIQ's intended use,
  the same "don't just trust the wrapper" caution any second-hand compiled dataset deserves.
- **Row count**: ~475,000 rows (as of 07/2025) across 2 CSV files (`Matches.csv`,
  `EloRatings.csv`), ~51 MB
- **Coverage**: **club** football — 27 countries, 42 leagues (including EPL, Bundesliga, La
  Liga), seasons 2000/01 through 2024/25. This is the club-scoped candidate §5's original research
  pass flagged as needing verification — now confirmed real, licensed, and structurally suitable.
- **Columns (Matches.csv)**: `Division` (league code — maps to `competition_ref`), `MatchDate`,
  `MatchTime`, `HomeTeam`, `AwayTeam`, `HomeElo`, `AwayElo`, form/streak fields, `FTHome`/`FTAway`
  (full-time score — maps directly to `HistoricalFixtureRecord.home_score`/`away_score`),
  `FTResult`, half-time scores, shots/corners/fouls/cards, and a large block of bookmaker-odds
  columns (`OddHome`/`OddDraw`/`OddAway`, `MaxHome`/`MaxDraw`/`MaxAway`, Asian handicap, over/under
  2.5 goals — Bet365 plus a ~17-bookmaker max-odds aggregate).
- **Note on the odds columns**: `CsvHistoricalSource`/`HistoricalImportService` as built this phase
  would only ever read `Division`/`MatchDate`/`HomeTeam`/`AwayTeam`/`FTHome`/`FTAway` via
  `CsvColumnMapping` — the odds columns are simply never mapped or read. TitanIQ already has its
  own real, licensed odds pipeline (`ProviderOddsRecord`/`fetch_odds` via API-Football,
  `FootballOddsFeatureWriter`) feeding actual prediction markets; this dataset's odds columns would
  be redundant historical betting-market data, not a new capability, and importing them was never
  part of this phase's scope. Not a compliance concern for the fixture-identity-only import this
  phase built, but flagged so a future session doesn't casually wire them in without checking
  TitanIQ's own prohibited-terminology/monetization product principles first.
- **This is now the strongest overall football candidate for a future real-import session** — CC0
  international data (§5 above) has zero license friction but limited overlap with TitanIQ's
  club-scoped live data; this MIT club-competition dataset has direct overlap with the 215 teams
  and 7 competitions already in `dev.db` and is structurally ready for
  `CsvHistoricalSource(columns=CsvColumnMapping(date="MatchDate", home_team="HomeTeam",
  away_team="AwayTeam", home_score="FTHome", away_score="FTAway", competition="Division"))` with
  no code changes needed.

## 6. Step 3–4 — Kaggle Dataset Research: Basketball

**Primary candidate — verified live, CSV, immediately usable: "NBA Dataset: Box Scores and Stats
(1947 - Today)"** (Kaggle: `eoinamoore/historical-nba-data-and-player-box-scores`)
- **Owner**: Eoin A Moore
- **License**: **CC0: Public Domain** (confirmed on the dataset's own License panel — the strongest
  possible license, no attribution or share-alike obligation)
- **Format**: **CSV** (plus one `.parquet` play-by-play file this phase's importer would never
  read) — directly compatible with `CsvHistoricalSource` as built, no new adapter needed.
- **Coverage**: every NBA game since the 1946–47 season, updated daily, box scores from all games
  since 1947, advanced stats since 1997.
- **Directly usable file — `Games.csv`**: `gameId`, `gameDateTimeEst`, `hometeamCity`,
  `hometeamName`, `hometeamId`, `awayteamCity`, `awayteamName`, `awayteamId`, `homeScore`,
  `awayScore`, plus arena/attendance where available — a clean, direct match for
  `HistoricalFixtureRecord`'s shape, ready for
  `CsvHistoricalSource(sport=SportCode.BASKETBALL, columns=CsvColumnMapping(date="gameDateTimeEst",
  home_team="hometeamName", away_team="awayteamName", home_score="homeScore",
  away_score="awayScore"))` with no code changes.
- **This supersedes the previously-noted `wyattowalsh/basketball` candidate** (CC BY-SA 4.0,
  DuckDB/SQLite only, no CSV export — would have required building a new `SqliteHistoricalSource`
  adapter first). This CSV, CC0 candidate needs no new adapter and carries a stronger license.
- Basketball is a real match for TitanIQ's own coverage: `api_basketball` is registered
  (Phase 3 capability matrix) and NBA is a plausible future competition to enrich.

## 7. Step 3–4 — Kaggle Dataset Research: Baseball

**Primary candidate — verified live, CSV, game-level, immediately usable: "MLB Game Data"**
(Kaggle: `cristobalmitchell/mlb-game-data`)
- **Owner**: Cristobal Mitchell
- **License**: **CC0: Public Domain** (confirmed on the dataset's own License panel)
- **Provenance**: data scraped from ESPN.com's public box scores via a scraping tool the uploader
  names ("SportScraper") — the Kaggle upload itself carries CC0, the same "wrapper license vs.
  underlying source" note as §5's football dataset applies here too; ESPN's own terms weren't
  independently re-checked this session.
- **Row count**: ~30,000 games (2010–2020 MLB seasons, regular season + preseason, per the
  dataset's own per-season row counts: roughly 3,000 games/season across 11 seasons)
- **Format**: CSV, 2 files (`mlb_games.csv`, `mlb_teams.csv`)
- **Columns (`mlb_games.csv`)**: `away_team`, `away_team_score`, `date`, `game_id`, `home_team`,
  `home_team_score`, `note`, `season`, `year` — a clean, direct game-level match for
  `HistoricalFixtureRecord`, ready for `CsvHistoricalSource(sport=SportCode.BASEBALL,
  columns=CsvColumnMapping(date="date", home_team="home_team", away_team="away_team",
  home_score="home_team_score", away_score="away_team_score"))` with no code changes. Team names
  are 2-3 letter codes (`chw`, `nyy`, …), not full names — `mlb_teams.csv` (not yet inspected in
  detail) likely carries the code-to-name mapping a real import would need to join first.
- **This supersedes the previously-noted `open-source-sports/baseball-databank` candidate**, whose
  game-log tables (`Parks.csv`/`HomeGames.csv`) were missing from that specific Kaggle upload — this
  dataset is genuinely game-level, confirmed by its own column list, not assumed.
- **Limitation, documented honestly**: 2010–2020 coverage only (not a multi-decade historical
  corpus like the football/basketball candidates above), and 11-season/~30K-row scale is modest
  next to the ~475K-row football candidate. Still a real, clean, immediately usable baseball
  candidate — better to report a smaller verified dataset than force a larger unverified one.

## 8. Step 3–4 — Kaggle Dataset Research: Table Tennis

**No suitable candidate found.** The only table-tennis datasets surfaced on Kaggle are a video/frame
dataset (`anshulmehtakaggl/table-tennis-games-dataset-ttnet` — computer-vision frames, not match
results) and two narrow, single-league one-month scrapes (`medaxone/one-month-table-tennis-dataset`,
`medaxone/one-month-ligapro-table-tennis-dataset` — a few thousand rows from one operator, not a
broad historical corpus). This is consistent with Phase 3's own finding that table tennis has **no
real provider at all** in TitanIQ (`PROVIDER_KEY_BY_SPORT` has no `table_tennis` entry, confirmed
again this phase, unchanged). **Reported as NONE, per the master prompt's own instruction not to
force a weak match** — no table-tennis historical source is recommended.

---

## 9. Step 5 — Kaggle Credential Status

Checked directly in this environment: `KAGGLE_USERNAME` and `KAGGLE_KEY` environment variables are
both **unset**; no `kaggle.json` exists at the default lookup path. Per the master prompt's
verbatim instruction:

> *"If actual download requires credentials that are unavailable: stop the download portion and
> document exactly what is blocked... Never place credentials into: source code, Git,
> documentation, database, command output."*

**The download portion of Step 5 is stopped here and documented as blocked.** No credentials were
fabricated, requested from the user in a way that would place them in this transcript, or worked
around by scraping Kaggle's site instead of using its API. Nothing beyond this documentation was
attempted for the download step. An operator who wants to run a real IMPORT in a future session
needs to supply `KAGGLE_USERNAME`/`KAGGLE_KEY` (or a `kaggle.json`) themselves, outside this
conversation, through their own environment configuration — never through this chat.

---

## 10. Step 6–7 — Historical Import Abstraction

New files (all additive — nothing existing was modified except one composition.py wiring addition,
§17):

- **`modules/ingestion/ports/historical_source.py`** — `HistoricalSourcePort` protocol
  (`source_key`, `read_records(file_path) -> HistoricalReadResult`) and `HistoricalReadResult`
  (`records`, `rejected`). Deliberately reads from a **local file path**, never a URL or live API —
  how the file reached disk (Kaggle download, manual upload) is out of this port's scope, which is
  exactly the boundary that makes Step 5's credential-safety rule structurally satisfiable: this
  port and everything built on it can be fully implemented, tested, and verified without ever
  touching Kaggle authentication.
- **`modules/ingestion/infrastructure/historical/csv_historical_source.py`** —
  `CsvHistoricalSource`, a generic (not Kaggle-specific) CSV reader with a configurable
  `CsvColumnMapping` (Kaggle football/basketball/baseball datasets each use their own header
  vocabulary, confirmed in §5–§7 — this is real, not a design choice made in a vacuum). Row-level
  validation rejects (not silently drops) rows missing a required field or with an unparseable
  date, surfaced as `QuarantinedRecord`s in `HistoricalReadResult.rejected`.

## 11. Canonical Historical Record Contract

**`modules/ingestion/domain/historical_import.py`** — `HistoricalFixtureRecord`: `source_key`,
`source_record_id` (idempotency key), `sport`, `competition_ref`, `competition_name`,
`season_label`, `scheduled_at`, `home_team_name`, `away_team_name`, `home_score`, `away_score`,
`neutral_venue`. Deliberately a *pre-resolution* DTO (raw strings, not yet `ProviderRef`s) — it
mirrors `ProviderFixtureRecord`/`ProviderTeamRecord`'s shape in spirit without duplicating them,
since a historical CSV row has no notion of any provider's internal identity yet. `ImportMode`
(`DRY_RUN`/`VALIDATE`/`IMPORT` — `IMPORT` never the default anywhere it's consumed),
`QuarantineReason`, `QuarantinedRecord`, `HistoricalImportReport` (the full accounting object:
`total_records`, `rejected_rows`, `fixtures_created/updated`, `teams_created/matched`,
`competitions_touched`, `quarantined`) all live here too.

---

## 12. Steps 8–11 — Validation, Reconciliation & Team Resolution Hierarchy

**`modules/ingestion/application/historical_import_service.py`** — `HistoricalImportService` is the
single orchestrator. It **writes nothing directly to any repository** — every write goes through
`EntityReconciliationService`'s existing `reconcile_team`/`reconcile_competition`/
`reconcile_season`/`reconcile_fixture` methods, or (for a team that resolves to an *existing* team)
a single `provider_ref_index` upsert using the same `ProviderRefIndexEntry` shape
`EntityReconciliationService` itself uses internally.

**Team resolution hierarchy** (implemented exactly, tested in
`test_historical_import_service.py`):

1. Exact normalized-name match (`CrossProviderTeamMappingService`'s own `_normalize_name`, reused
   directly — not reimplemented) against **exactly one** existing team for the sport → reuse it,
   recorded via a new `provider_ref_index` row pointing the historical ref at the existing team id.
2. Exact normalized-name match against **2+** existing teams (genuine ambiguity — e.g. two
   differently-provider-sourced teams that happen to normalize the same way) → the whole record is
   **quarantined** (`QuarantineReason.AMBIGUOUS_TEAM`), never guessed.
3. **No match at all** → a new team is created via `reconcile_team` — this is historical
   enrichment's actual job (Kaggle rosters routinely include clubs/countries no live provider has
   synced), not a failure case.

**Competition/season scoping**: a historical source's competitions and seasons reconcile into their
**own `historical:{source_key}` provider namespace** — they never auto-merge onto an existing
live-provider competition (e.g. api-football's own "English Premier League") purely on a name
match. This is the direct, conservative answer to the master prompt's own EPL/Premier
League/English Premier League warning: auto-merging competitions on name similarity is exactly the
kind of guess Phase 4 was told not to make. An operator can merge a historical competition into an
existing one later via the same admin tooling any cross-provider competition merge already uses;
Phase 4 does not build that merge tool itself (out of scope — not requested).

**Idempotency**: re-importing the identical file a second time creates zero duplicate teams and
zero duplicate fixtures — proven by `test_reimporting_the_same_file_is_idempotent`. This falls out
for free from `EntityReconciliationService`'s own `(provider, external_id)` identity resolution;
`HistoricalImportService` adds no deduplication logic of its own.

---

## 13. Steps 12–15 — Source Attribution, Provenance, Score Preservation, Conflict Handling

- **Source attribution**: every write carries a `ProviderRef(provider=f"historical:{source_key}",
  external_id=...)`, stored exactly where every other provider's refs are stored
  (`Team.provider_refs`, `Fixture.provider_refs`, `provider_ref_index`) — no new columns, no
  redundant schema, confirmed not needed per Step 12's own "no redundant columns unless proven
  necessary" instruction.
- **`SyncTrigger.BACKFILL`**: every IMPORT-mode run creates a `SyncRun` row tagged
  `trigger=SyncTrigger.BACKFILL`, `scope_key=f"historical:{source_key}"` — proven by
  `test_import_records_a_sync_run_tagged_backfill`. DRY_RUN and VALIDATE modes create **no**
  `SyncRun` at all (nothing was actually synced) — proven by `test_dry_run_creates_no_sync_run`.
- **Score preservation**: `reconcile_fixture` is always called with `preserve_existing_score=True`.
  `test_historical_import_never_overwrites_an_existing_authoritative_score` seeds a fixture with a
  real 9–9 score from `api_football`, then imports a historical row for the same two teams/date
  reporting 1–2 — the existing 9–9 score survives unchanged, and the historical row converges onto
  the *same* fixture (via `match_by_teams_and_date=True`, also always-on) rather than creating a
  duplicate.
- **Conflict handling**: a genuinely ambiguous record (2+ matching teams) is quarantined, never
  silently resolved by picking one candidate — the same "quarantine, never guess" principle applies
  uniformly to teams and would apply identically to any future competition-alias ambiguity.

---

## 14. Steps 16–19 — Feature Safety, Leakage Prevention, Training Safety, Gated-Feature Exclusion

`HistoricalImportService` writes **fixture identity and final score only** — it never writes a
Feature Store value, never touches `DatasetBuilder`, `TrainingPreflightService`, or any Champion
model artifact, and never calls `classify_availability`. This is a structural guarantee, not a
policy one: there is no code path from this service into feature writing at all (§3, §12).

Consequently:
- **Leakage**: cannot occur, because nothing this service writes is ever read as a pre-match
  feature. The only leakage-relevant fact a historical row carries — its final score — is exactly
  the same kind of "outcome" data every other provider's `reconcile_fixture` call already writes,
  through the identical code path, with identical `preserve_existing_score` protection.
- **Gated pre-match intelligence** (lineup continuity, transfer activity, news impact): untouched.
  `HistoricalImportService` has no method that writes a `Lineup`, `Injury`, `Transfer`, or news
  event — those remain solely the live-scheduled pipeline's responsibility, exactly as the master
  prompt requires.
- **Training**: `DatasetBuilder`/`TrainingPreflightService`/`AutomaticModelSelectionService` were
  not modified, imported by, or called from any Phase 4 file. Historical import cannot auto-trigger
  training because it contains no reference to any training entry point.
- `test_historical_fixture_never_becomes_verified_pre_match` confirms the persisted `FixtureModel`
  row carries no `availability_classification` attribute at all (that field doesn't exist on the
  base fixture schema — it's specific to the structured-intelligence entities this service never
  writes).

---

## 15. Steps 20–21 — Multi-Source Convergence & Zero-Waste API Calls

- **Convergence**: `match_by_teams_and_date=True` (already-existing, already-tested mechanism) lets
  a historical row converge onto a fixture any live provider already created for the same two
  teams within a 1-day window, rather than creating a duplicate — proven in §13's score-preservation
  test, where the historical import updates (not duplicates) the api-football-sourced fixture.
- **Zero-waste external calls**: `HistoricalImportService` makes **zero** network calls of any
  kind — `CsvHistoricalSource.read_records` only ever opens a local file. There is no quota,
  rate-limit, or circuit-breaker concern for historical import at all, since it never touches
  `SportsProviderRouter`, `QuotaIntelligenceEngine`, or `CircuitBreaker` — those Phase 2 primitives
  govern *live* provider calls, which this service structurally cannot make.

---

## 16. Steps 22–27 — Modes, Quarantine, Transactions, Batching, Schema, Tests

- **Modes**: `ImportMode.DRY_RUN` and `ImportMode.VALIDATE` perform **zero repository writes** —
  proven by `test_dry_run_and_validate_never_write_to_the_database` (parametrized over both modes,
  asserting `TeamModel`/`FixtureModel` tables stay empty). Both still compute an honest
  would-create/would-update fixture count via a single read-only `provider_ref_index.get()` lookup
  — no write of any kind occurs to produce that count. `ImportMode.IMPORT` is never the default
  parameter anywhere it's consumed; every call site must pass it explicitly.
- **Quarantine reporting**: `HistoricalImportReport.quarantined` carries every rejected/ambiguous
  record with its `QuarantineReason` and a human-readable detail string — nothing is silently
  dropped. `total_records = len(records) + len(rejected)` so the report's own arithmetic proves
  nothing was lost between "read from file" and "accounted for."
- **Transaction/checkpoint safety**: each record's reconciliation happens through the same
  `AsyncSession`-scoped calls every other sync path already uses (no new transaction boundary
  introduced); a `SyncRun` row records `records_fetched/created/updated/rejected` at the end of an
  IMPORT run, matching the exact shape `IngestionQualityEngine` already reads for every other sync.
- **Batching**: not implemented as a separate optimization this phase — CSV row-by-row reconciliation
  through `EntityReconciliationService` is the same per-record cost every live provider sync already
  pays; no dataset was large enough in this session's testing to require batching, and no real
  dataset was imported at all (§9). Flagged here, not silently absorbed, as a real future
  consideration once an actual multi-thousand-row file is run.
- **Schema**: no migration was needed or written — every write goes through existing
  `Team`/`Competition`/`Season`/`Fixture`/`provider_ref_index`/`SyncRun` tables, unchanged.
- **Tests**: see §18.

---

## 17. Files Created / Modified

**Created:**
- `backend/modules/ingestion/domain/historical_import.py`
- `backend/modules/ingestion/ports/historical_source.py`
- `backend/modules/ingestion/infrastructure/historical/__init__.py`
- `backend/modules/ingestion/infrastructure/historical/csv_historical_source.py`
- `backend/modules/ingestion/application/historical_import_service.py`
- `backend/tests/unit/modules/ingestion/test_historical_import_service.py`
- `backend/docs/post_m24_master_data_fabric_phase4_verification_report.md` (this file)

**Modified:**
- `backend/apps/api/composition.py` — one new import
  (`HistoricalImportService`) and one new additive factory
  (`build_historical_import_service`), placed immediately after
  `build_entity_reconciliation_service`. No existing factory, route, or Celery wiring changed.

Nothing else in the repository was touched this phase.

---

## 18. Test Coverage Summary

`test_historical_import_service.py` — **16 tests, all passing**, real DB round-trips against an
in-memory SQLite database (same pattern as `test_entity_reconciliation_service.py`):

| Category | Tests |
|---|---|
| CSV source row-level validation | 4 (valid parse, missing team name, unparseable date, missing scores) |
| Team resolution hierarchy | 3 (new-team creation, exact-match reuse, ambiguous-match quarantine) |
| Mode gating (DRY_RUN/VALIDATE never write) | 2 (parametrized zero-write assertion, IMPORT-mode real persistence) |
| Idempotency | 1 (re-import produces zero duplicates) |
| Score preservation / multi-source convergence | 1 (existing authoritative score survives a historical import for the same fixture) |
| Provenance | 3 (SyncRun tagged BACKFILL, no SyncRun in DRY_RUN, no availability_classification ever set) |
| Precondition enforcement | 1 (importing for a sport that was never reconciled raises, rather than silently creating one) |
| Report arithmetic | (covered inline across the above — `total_records`/`quarantined_count` asserted throughout) |

Full `tests/unit/modules/ingestion/` suite (239 tests, includes the 16 new ones plus every
pre-existing ingestion test from Phases 1–3): **239 passed, 0 failed** — zero regressions in the
module this phase touched.

---

## 19. Step 28 — Real Dataset Decision & Import Status

**No real import was executed.** Per §9, Kaggle credentials are unavailable in this environment, so
the download portion required before any real IMPORT run is blocked and documented rather than
worked around. Consequently:

- **Real rows imported**: 0
- **Real dataset license used**: none (no real dataset was downloaded)
- **Recommended real candidate for a future session** (once an operator supplies Kaggle
  credentials): `adamgbor/club-football-match-data-2000-2025` (§5, MIT, license-verified,
  structurally ready, direct club-competition overlap with existing `dev.db` data) for a first
  real DRY_RUN → VALIDATE → IMPORT run. The CC0 international-results dataset (§5) remains a solid
  second choice once national-team coverage specifically is wanted.

## 20. Step 29 — Post-Import Verification

**Not applicable — no real import ran.** Once a future session performs a real IMPORT, this section
should be re-run and should explicitly re-verify: row-count deltas, zero duplicate fixtures/teams,
correct canonical entity resolution, `SyncTrigger.BACKFILL` on every new `provider_ref_index`
row this phase's namespace produced, zero change to `predictions`/`prediction_outcomes`/`models`
counts, and an explicit `TrainingPreflightService` run confirming increased historical volume was
**not** treated as training authorization.

---

## 21. Step 30 — Full Regression Suite

Targeted `tests/unit/modules/ingestion/` run: **239 passed, 0 failed** (includes all 16 new Phase 4
tests plus every pre-existing ingestion test — zero regressions).

Full backend suite (`pytest -q`, all modules): **2350 passed, 58 skipped, 0 failed** (1122.54s /
18m43s). Delta vs. the Phase 3 baseline (2334 passed / 58 skipped / 0 failed) is exactly **+16
passed, 0 skipped change, 0 failed** — precisely the 16 new `test_historical_import_service.py`
tests, with zero regressions anywhere else in the suite.

---

## 22. Database Integrity Verification

`dev.db` was never written to during this phase — every test in `test_historical_import_service.py`
runs against an isolated in-memory SQLite database, matching the existing convention for
reconciliation-service tests. The Step 2 baseline (§4) remains the exact current state of `dev.db`:
zero drift.

---

## 23. Reused vs. New Components

**Reused, unchanged:**
`EntityReconciliationService` (all four `reconcile_*` methods it already had),
`match_by_teams_and_date`, `preserve_existing_score`, `provider_ref_index` / `ProviderRefIndexEntry`,
`_normalize_name` (imported, not duplicated), `SyncTrigger.BACKFILL`, `SyncRun` /
`SyncRunRepositoryPort`, `SqlAlchemySyncRunRepository`, `Fixture`/`Team`/`Competition`/`Season`
domain entities and repositories, `ProviderFixtureRecord`/`ProviderTeamRecord` DTOs, `SportCode`,
`normalize_provider_fixture_status`'s existing `"FT"`/`"NS"` status vocabulary.

**New, additive only:**
`HistoricalFixtureRecord`/`ImportMode`/`HistoricalImportReport`/`QuarantinedRecord` (domain),
`HistoricalSourcePort` (port), `CsvHistoricalSource` (one infrastructure adapter),
`HistoricalImportService` (one application service), one composition.py factory.

No second reconciliation engine, no second provider registry, no schema migration, no new
`EntityKind`, no new `SyncTrigger` value — every extension point the master prompt named as
off-limits was left off-limits.

---

## 24. Provenance & Leakage Safety Guarantees

1. Every historical write is tagged `SyncTrigger.BACKFILL` on its `SyncRun`.
2. No historical write ever sets, reads, or is affected by `VERIFIED_PRE_MATCH` /
   `classify_availability` — that machinery is structurally out of this service's reach (§14).
3. A historical row's own `home_score`/`away_score` never overwrites an existing authoritative
   score (`preserve_existing_score=True`, always-on, tested).
4. Historical import never writes a `Lineup`/`Injury`/`Transfer`/news event — gated pre-match
   intelligence remains solely the live-scheduled pipeline's responsibility.
5. Historical import never calls `DatasetBuilder`, `TrainingPreflightService`, or any training
   entry point — increased historical row count cannot auto-trigger training because no code path
   connects the two.

---

## 25. Known Limitations & Scope Boundaries

- No real Kaggle data was ever downloaded or imported this session (§9, §19) — everything is
  built and proven against representative CSV fixtures, not the actual named datasets.
- Two football candidates are now fully verified: a CC0 international-results dataset (limited
  overlap with TitanIQ's club-scoped live data) and an MIT club-competition dataset with direct
  overlap with the 215 teams / 7 competitions already in `dev.db` — see §5 for both. The club one
  is the stronger choice for a first real import.
- The basketball and baseball candidates now verified (§6, §7) are both CC0, CSV, game-level, and
  immediately usable with `CsvHistoricalSource` as built — no remaining format gap for either sport.
  The baseball candidate's coverage (2010–2020, ~30K rows) is comparatively modest next to the
  football and basketball candidates' multi-decade scale — a real limitation of that specific
  dataset, not of the importer.
- No competition-alias admin UI/endpoint was built — an operator merging a historical-source
  competition into an existing live-provider competition is a manual `provider_ref_index`
  operation today, same as any other cross-provider entity merge in this codebase.
- Batching for very large files was not implemented — flagged (§16), not silently absorbed.

---

## 26. Risks & Recommendations for a Future Real-Data Import Session

1. Supply Kaggle credentials outside this conversation (never paste them into chat).
2. Start with the MIT club-football dataset (`adamgbor/club-football-match-data-2000-2025`, §5) in
   DRY_RUN mode against the full real ~475,000-row file using the `CsvColumnMapping` given in §5 —
   it has the most real overlap with TitanIQ's existing club-competition data, so its quarantine
   report (ambiguous team names, competition-alias gaps) will be the most representative signal.
   Review the report, then VALIDATE, then IMPORT. Spend one minute confirming Football-Data.co.uk's
   own terms before that IMPORT, per §5's note.
3. The CC0 international-results dataset remains a good second candidate once national-team
   coverage is wanted, despite its lower overlap with existing club data.
4. For basketball, use `eoinamoore/historical-nba-data-and-player-box-scores` (§6, CC0, CSV,
   `Games.csv`) — no `SqliteHistoricalSource` build-out needed, it works with the existing
   `CsvHistoricalSource` today.
5. For baseball, use `cristobalmitchell/mlb-game-data` (§7, CC0, CSV, `mlb_games.csv`) — note its
   team names are short codes (`chw`, `nyy`), so a real import should first inspect
   `mlb_teams.csv` for the code-to-name mapping before choosing team-resolution inputs.
6. Re-run `TrainingPreflightService` after any real IMPORT and confirm it still reports whatever
   pre-existing gates it already enforces — never treat new historical rows as training
   authorization.

---

## 27. Non-Negotiable Rules Compliance Checklist

| Rule | Status |
|---|---|
| Historical data never becomes `VERIFIED_PRE_MATCH` | PASS — structurally unreachable (§14, §24) |
| `SyncTrigger.BACKFILL` on every historical write | PASS — tested (§13, §18) |
| No Kaggle credentials fabricated/bypassed/scraped-around | PASS — documented blocker only (§9) |
| No credentials placed in code/git/docs/DB/output | PASS |
| Reuse `EntityReconciliationService`, no second engine | PASS (§23) |
| Reuse `provider_ref_index`, no second index | PASS (§23) |
| No gated pre-match feature satisfied by Kaggle data | PASS — no feature ever written (§14) |
| `DatasetBuilder`/`TrainingPreflightService` untouched | PASS (§3, §14) |
| No auto-triggered training | PASS — no code path exists |
| IMPORT mode never default | PASS (§16) |
| No schema migration without proven need | PASS — none needed, none written |
| Existing higher-authority live data preserved | PASS — `preserve_existing_score`, tested |

---

## 28. Acceptance Criteria vs. Master Prompt

All Phase 4 steps (1–27, 30–31) were completed to the extent achievable without real Kaggle
credentials. Steps 28–29 (real dataset report, post-import verification) are explicitly marked
not-applicable rather than fabricated, per §19–§20.

---

## 29. What Was NOT Done (Explicit)

- No real Kaggle dataset was downloaded.
- No real IMPORT-mode run against real data occurred.
- No Champion model, calibration, training run, or market catalog was touched.
- No Celery Beat schedule was added or started.
- No admin UI/endpoint for triggering historical import was built (not requested; out of this
  phase's own scope, which was the import subsystem itself).
- No competition-alias merge tool was built.
- No `SqliteHistoricalSource` was built (no CSV-format basketball/baseball candidate to exercise it
  against this session).

---

## 30. Final Response Format

```
PHASE 4 STATUS: COMPLETE (subsystem built, tested, verified — real-data import blocked on missing
                Kaggle credentials, documented per Step 5's own instruction, not worked around)
HISTORICAL IMPORT ABSTRACTION: PASS — HistoricalSourcePort + HistoricalImportService, reuses
                EntityReconciliationService verbatim, zero new reconciliation logic
KAGGLE DATASET (FOOTBALL): FOUND (2 verified) — adamgbor/club-football-match-data-2000-2025
                (MIT, ~475,000 rows, club football, 42 leagues, direct overlap with existing data
                — strongest candidate) and martj42/international-football-results-from-1872-to-2017
                (CC0, 49,393 rows, international football, secondary candidate)
KAGGLE DATASET (BASKETBALL): FOUND — eoinamoore/historical-nba-data-and-player-box-scores, CC0,
                CSV (Games.csv), NBA 1946-present, immediately usable with CsvHistoricalSource
KAGGLE DATASET (BASEBALL): FOUND — cristobalmitchell/mlb-game-data, CC0, CSV (mlb_games.csv),
                MLB 2010-2020 (~30K games), immediately usable with CsvHistoricalSource
KAGGLE DATASET (TABLE TENNIS): NONE — no broad historical results dataset exists
LICENSE VERIFICATION: PASS — verified live via browser render, never guessed
CREDENTIAL STATUS: BLOCKED — no Kaggle credentials in this environment; documented, not bypassed
REAL IMPORT EXECUTED: NO
ROWS IMPORTED (REAL DATA): 0
PROVENANCE SAFETY: PASS — SyncTrigger.BACKFILL only, VERIFIED_PRE_MATCH unreachable
LEAKAGE PREVENTION: PASS — no feature ever written by this service
GATED FEATURE EXCLUSION: PASS — Lineup/Injury/Transfer/news untouched by historical import
TRAINING SAFETY: PASS — no code path from historical import to DatasetBuilder/training
SCORE PRESERVATION: PASS — preserve_existing_score=True, tested
IDEMPOTENCY: PASS — tested, zero duplicates on re-import
DATABASE SCHEMA: UNCHANGED — no migration written or needed
DATABASE INTEGRITY: PASS — dev.db untouched, zero drift from Phase 3 baseline
INGESTION MODULE TESTS: 239 passed, 0 failed (16 new)
BACKEND TESTS (FULL SUITE): 2350 passed, 58 skipped, 0 failed (baseline 2334/58/0 -> +16, exact
                match to the 16 new tests, zero regressions)
NEXT PHASE: PHASE 5 — requires new explicit authorization
STOP COMPLETELY: YES — no auto-proceeding to Phase 5, no training, no Champion changes, no
                unattended Celery Beat
```
