# Historical Data Expansion Audit — Kaggle Feasibility

**Date:** 2026-08-14
**Status:** Analytical phases (1–9) complete. Acquisition phases (7 data-quality-on-real-data,
10–14) not started — see §17 for why, and the decision this report asks for.
**Scope:** Operational historical-data-expansion task, per explicit user instruction. **Not**
Milestone 25 — Milestone 24 remains the final milestone of the TitanIQ engagement.

---

## 1. Executive summary

**The central finding of this audit: no Kaggle dataset — however large, clean, or well-matched —
can move any of TitanIQ's 14 genuinely-trained football markets from BLOCKED to READY.**

This is not a data-quality or data-volume conclusion. It is architectural. Re-running
`TrainingPreflightService` fresh today (§15) confirms that on every one of the 14 markets, the
`required_feature_coverage_acceptable` and `training_inference_feature_parity` gates fail **only**
on gated intelligence features — `{home,away}_lineup_continuity`, `{home,away}_transfer_activity`,
and (on 12/14 markets) `news.football.{home,away}_*_impact`. Every non-gated required feature
(odds-derived implied probabilities, form differentials, expected goals) already has acceptable
coverage using TitanIQ's existing data. The gated features are, by explicit and doubly-enforced
design (`modules/ingestion/application/provenance.py:121`, `modules/intelligence/application
/news_provenance.py:70`), only ever produced by `SyncTrigger.LIVE_SCHEDULED` — a live, real-time
sync that observes a fact before a specific fixture's kickoff and records that timing. A historical
archive dataset assembled after the fact has no way to prove "this was known and verified before
kickoff" for any given row, so it can never legitimately satisfy those checks, at any volume.

This means the task's literal objective — "give TitanIQ enough data that the training gate can
legitimately decide a model is ready" — **cannot be achieved by importing Kaggle data**, because
data volume was never the blocking dimension for these 14 markets. The blocking dimension is real
time itself: real fixtures have to actually approach kickoff while TitanIQ's own live pipeline
(fixed and verified in M24) is running, for genuine `VERIFIED_PRE_MATCH` observations to ever
accumulate. This restates, from a completely different angle (external-data feasibility instead of
internal-pipeline correctness), the same structural blocker M17–M24 already established.

**What Kaggle data legitimately could do**, separate from the blocked gate: expand the *volume and
statistical robustness* of the non-gated dimensions (raw fixture/result coverage, odds history,
box-score-derived form/expected-goals features) for leagues or seasons where TitanIQ's own live
providers have sparser historical coverage. This has real value for eventual training quality once
the gated-feature blocker is separately resolved by real time passing — but it is a quality/breadth
improvement to data that is already sufficient, not a fix for what is actually blocking readiness.

Given this, §17 asks for a decision before any Kaggle data is actually acquired.

## 2. Current TitanIQ training state

Unchanged from the M24 final report: **STATE A**. 0/14 markets ready. 47 `models` rows, 12,436
`predictions`, 71,223 `feature_values_offline` rows, 6,834 `fixtures`, 308 `transfers`, 68
`news_events` (0 `VERIFIED_PRE_MATCH`), 0 `datasets` (see §6 correction). All row counts captured
fresh as a pre-audit baseline (§16); `dev.db` has not been written to during this audit.

## 3. Existing API coverage

Confirmed live, real, currently operational (per M21–M24): API-Football (primary sports provider,
injuries/transfers/coaching-staff/lineups/players), football-data.org (opt-in fixture-schedule
path for EPL), API-Basketball/API-Baseball (secondary sports), 8 RSS feeds (BBC, ESPN×2, 90min,
Guardian, NYT Athletic×2, MLB.com), Gemini (news enrichment, credentialed, cost-gated by relevance
filter). None of these were touched during this audit — no external API call was made except to
Kaggle's public dataset pages (read-only, no download).

## 4. Kaggle candidates investigated

Web search + direct inspection of the highest-signal results:

| Dataset | Publisher | Coverage | License | Verdict |
|---|---|---|---|---|
| **Club Football Match Data (2000–2025)** | Adam Gábor | 27 countries, 42 leagues, 2000/01–2024/25, ~475K rows, 2 CSVs (Matches, EloRatings) | **MIT** | **PRIMARY CANDIDATE** |
| European Soccer Database | Hugo Mathien | 11 countries, 2008–2016, ~25K matches, lineups+FIFA player attributes+odds | "Open Database, Contents © Original Authors" — explicit non-commercial restriction ("I must insist that you do not make any commercial use of the data") | **Rejected** (§5) |
| Soccer Bet: Euro Data 1993–2023 | laisassini | Odds-focused, long history | Not inspected in detail — superseded by primary candidate's broader coverage | Not selected |
| Historical Football Results/Betting Odds Data | mexwell | Odds-focused | Not inspected in detail | Not selected |
| Top 5 European Leagues Dataset | enricocattaneo | 2016/17–2021/22, Sportmonks-sourced, includes lineups/events | Not inspected — narrower season range than primary, and (per its own description) includes lineup data with the same "no pre-match timestamp provenance" problem as the rejected candidate | Not selected |

No dataset offering genuine, timestamped, pre-match-verifiable lineup/transfer/injury/news data was
found or expected to exist — this is not a Kaggle-search limitation, it is the general nature of
archival sports datasets, which are compiled after matches complete.

## 5. Selected dataset

**PRIMARY CANDIDATE: "Club Football Match Data (2000–2025)" by Adam Gábor**
(`kaggle.com/datasets/adamgbor/club-football-match-data-2000-2025`)

Why it is superior to every alternative found:
- **Source provenance is itself reputable and traceable**: match results/statistics sourced from
  Football-Data.co.uk (a long-established, widely-cited football data aggregator used by
  academic/industry research for two decades); Elo ratings from ClubElo (a well-known independent
  rating system). Not a scraped or unattributed compilation.
- **MIT license** — the only candidate with an unambiguous, permissive license. The runner-up
  (European Soccer Database) explicitly restricts commercial use, which is disqualifying given
  TitanIQ is a commercial product.
- **Largest and most current**: ~475,000 rows, 42 leagues, updated monthly, through July 2025 —
  the rejected alternative stopped in 2016 (10 years stale).
- **Structurally the safest possible candidate for this specific task**: it contains **zero**
  lineup, transfer, injury, or player-level fields. There is nothing in this dataset that could
  even be *tempting* to misclassify as a gated pre-match intelligence feature — the entire
  gated-feature risk surface (Phase 9) is moot for this dataset by construction, not by policy
  discipline. A dataset like the rejected one, which *does* carry lineup data with no timestamp
  provenance, would have required much more careful (and inherently riskier) judgment calls about
  what to reject; this one requires none.

**No secondary candidate is recommended.** Given §1's finding, a secondary dataset would only be
useful if it could plausibly fill a gap the primary leaves — and the only gaps the primary leaves
(lineups, transfers, news) are exactly the gated features that no historical dataset can honestly
satisfy regardless of which one is chosen. Selecting a second dataset with lineup/transfer data
(like the rejected candidate) would only reintroduce the misclassification risk without addressing
the actual blocker.

## 6. Dataset schema (primary candidate)

**File 1 — `EloRatings.csv`** (~9.9MB, 895K rows): `Date` (date), `Club` (string, remapped to
match `Matches.csv` naming), `Country` (3-letter code), `Elo` (float).

**File 2 — `Matches.csv`** (the training-relevant file), 52 columns total. Full column list, by
group:

- **Identity/time**: `Division` (country+division code, e.g. `E0`=English Premier League,
  `I1`=Italian Serie A — standard Football-Data.co.uk convention), `MatchDate` (YYYY-MM-DD),
  `MatchTime` (HH:MM:SS, CET-1), `HomeTeam`, `AwayTeam` (English club names, abbreviated).
- **Pre-match strength/form**: `HomeElo`, `AwayElo`, `Form3Home/Away`, `Form5Home/Away` (points
  gathered in last 3/5 matches).
- **Result (label source)**: `FTHome`, `FTAway`, `FTResult` (H/D/A), `HTHome`, `HTAway`, `HTResult`.
- **Match statistics**: `HomeShots`/`AwayShots`, `HomeTarget`/`AwayTarget` (shots on target),
  `HomeFouls`/`AwayFouls`, `HomeCorners`/`AwayCorners`, `HomeYellow`/`AwayYellow`,
  `HomeRed`/`AwayRed`.
- **Odds**: `OddHome`/`OddDraw`/`OddAway` (Bet365), `MaxHome`/`MaxDraw`/`MaxAway` (best of ~17
  bookmakers), `Over25`/`Under25`/`MaxOver25`/`MaxUnder25`, `HandiSize`/`HandiHome`/`HandiAway`
  (Asian handicap).
- **Derived match-style clusters**: `C_LTH`/`C_LTA`/`C_VHD`/`C_VAD`/`C_HTB`/`C_PHB` (6 columns,
  proprietary tempo/dominance clustering — not TitanIQ-relevant, would be dropped).

## 7. Licensing/provenance

MIT license — permits commercial use, modification, and redistribution with attribution. Source
attribution is itself traceable (Football-Data.co.uk + ClubElo, both stated on the dataset page).
No authentication beyond a standard Kaggle account is needed to download (§17).

## 8. Data quality

**Not yet assessed on the real file** — this requires downloading the CSV, which this audit
deliberately has not done (§17). The dataset page itself states ~475K rows / ~51MB / 2 files, MIT
license, "Usability 10.00" (Kaggle's own completeness/documentation score), updated monthly. A real
quality audit (duplicate rows, missing labels, impossible scores, invalid dates, season/competition
consistency per the master prompt's season/league/competition-integrity requirements) is Phase 7
work that has not been performed and should not be assumed complete from the dataset page alone.

## 9. Fixture matching

This is the second most important finding of this audit, independent of the gated-feature blocker.

**TitanIQ's existing fixture-reconciliation pipeline cannot match raw team-name strings at all.**
`EntityReconciliationService.reconcile_fixture` (`modules/ingestion/application
/entity_reconciliation_service.py:400-453`) has exactly two paths:

1. **Primary path**: exact `(provider, external_id)` lookup via `ProviderRefIndexRepositoryPort`.
   Requires the incoming record to already carry a provider-specific external ID matching an
   already-known team/fixture. A Kaggle CSV has no such ID — it has only English club-name strings.
2. **Opt-in fallback**: `match_by_teams_and_date`, but this compares **internal `TeamId` UUIDs**
   (not name strings) plus a 1-day `scheduled_at` window. It requires teams to already be resolved
   to canonical IDs *before* this runs — it does not, and structurally cannot, match on raw names.

The only team-name-based matching that exists anywhere in the codebase,
`CrossProviderTeamMappingService` (`modules/ingestion/application
/cross_provider_team_mapping_service.py`), is narrow and admin-in-the-loop by design: exact
normalized-string match only (NFKD diacritic-stripping, lowercase, strip "FC"/"CF"/"SC" suffixes —
no fuzzy/edit-distance logic at all), binary 1.0/0.0 confidence, ambiguous collisions resolved by
silently keeping "whichever was seen first" (not flagged), hardcoded to the `football_data_org`
provider name, and its only write path (`confirm_mappings`) requires an explicit human-confirmed
list — it is a suggest-then-confirm admin tool, not something wired into `reconcile_fixture`.

**Consequence**: reliably matching ~475K Kaggle rows' `HomeTeam`/`AwayTeam` strings against existing
TitanIQ `Team` UUIDs would need new matching logic this codebase does not currently have anywhere
in its core pipeline. This is buildable (normalize names both ways, exact-match first, flag
everything else `AMBIGUOUS`/`UNMATCHED` rather than guess, per the master prompt's own required
hierarchy), but it is real, non-trivial engineering surface, and per the master prompt's Phase 11
principle ("prefer adapters over changes to established training infrastructure... if a change is
necessary, STOP and present it before applying"), building a new general-purpose fuzzy matcher
would be exactly this kind of change requiring explicit sign-off before implementation — separate
from and in addition to the gated-feature blocker in §1.

## 10. Feature mapping (Kaggle field → TitanIQ feature, non-gated only)

| Kaggle field | TitanIQ target | Notes |
|---|---|---|
| `MatchDate` + `MatchTime` | `Fixture.scheduled_at` | Combine; CET-1 → UTC conversion needed |
| `Division` | `Competition` (via country+division code → TitanIQ competition mapping) | New mapping table needed; not all 42 Kaggle leagues exist in TitanIQ today |
| `HomeTeam` / `AwayTeam` | `Team.id` | **Requires new matching logic — see §9** |
| `FTHome` / `FTAway` | `Fixture.home_score` / `away_score` → label source for `OutcomeResolutionService` resolvers | Direct, once fixture exists |
| `HomeShots`/`AwayShots`, `HomeTarget`/`AwayTarget`, `HomeCorners`/`AwayCorners`, `HomeFouls`/`AwayFouls`, `HomeYellow`/`AwayYellow`/`HomeRed`/`AwayRed` | `TeamStatistics` rows → feeds `FixtureFormDifferentialCalculator`'s existing rolling-differential computation | Same shape TitanIQ's own API-Football sync already writes |
| `OddHome`/`OddDraw`/`OddAway` | `football.market.implied_probability_home/away`, `overround` | Already-passing features (§1) — Kaggle odds would only add historical breadth, not fix a gap |
| `Form3Home/Away`, `Form5Home/Away`, `HomeElo`/`AwayElo` | Not directly mapped — TitanIQ computes its own rolling form via `FixtureFormDifferentialCalculator`, not from a pre-computed source field | Would be recomputed from imported `TeamStatistics`, not copied |
| `HTHome`/`HTAway`/`HTResult` | Not used by any of the 14 markets in scope (first_half_winner etc. are outside the genuinely-trained 14) | Out of scope |
| `C_LTH`/`C_LTA`/`C_VHD`/`C_VAD`/`C_HTB`/`C_PHB` | No TitanIQ equivalent | Would be dropped |
| *(nothing in this file)* | `football.fixture.{home,away}_lineup_continuity`, `{home,away}_transfer_activity`, `news.football.*_impact` | **Not present in this dataset at all — confirms §5's "safest possible candidate" framing** |

## 11. Market-by-market coverage

| Market | Current rows | Kaggle can supply label? | Kaggle can supply non-gated required features? | Kaggle can supply gated required features? | Provenance status if imported | Training impact |
|---|---|---|---|---|---|---|
| `football.correct_score` | (dataset never persisted, §6 correction — preflight rebuilds fresh each run; last run: reproducible content_hash confirmed) | Yes (`FTHome`/`FTAway`) | Partial — `expected_home/away_goals` already ungated & already passing | **No** — `home/away_lineup_continuity`, `home/away_transfer_activity` | Gated features: `INSUFFICIENT_PROVENANCE` (never eligible) | **None** — blocked identically before and after import |
| `football.total_goals_over_under` (+4 line variants) | — | Yes | Partial (already passing) | **No** — same 4 lineup/transfer + `news.*_goal_impact`×2 | Same | **None** |
| `football.home_team_total_goals` / `away_team_total_goals` | — | Yes | Partial (already passing) | **No** — same pattern | Same | **None** |
| `football.home_clean_sheet` / `away_clean_sheet` | — | Yes | Partial (already passing) | **No** — lineup/transfer + `news.*_clean_sheet_impact`×2 | Same | **None** |
| `football.home_win_to_nil` / `away_win_to_nil` | — | Yes | Partial (already passing) | **No** — same pattern | Same | **None** |
| `football.match_winner` | 658 samples (last real preflight run) | Yes (`FTResult`) | Already passing (`form_shots_on_target_diff_last5`, odds) | **No** — same 4 lineup/transfer keys | Same | **None** |
| `football.both_teams_to_score` | 653 samples | Yes | Already passing | **No** — 4 lineup/transfer + `news.*_btts_impact`×2 | Same | **None** |

Every row reaches the identical conclusion for the identical reason: the blocking features are
100% gated, 0% volume-addressable. "Rejected rows" / "eligible rows" breakdowns by
competition/season (as the master prompt's season-integrity section requests) are not meaningful
to produce here, because even a 100%-eligible, 100%-matched import changes zero markets' readiness.

## 12. Gated-feature analysis (Phase 9, answered directly)

For each of the 4 feature families gated by `VERIFIED_PRE_MATCH`:

| Feature family | A. Historical timestamp exists in Kaggle data? | B. Availability-before-kickoff provable? | C. Entity historically resolvable? | D. Compatible with TitanIQ's calculation? | E. Can legitimately enter training? |
|---|---|---|---|---|---|
| Lineup continuity | **No** — dataset has no lineup data at all | N/A | N/A | N/A | **No** |
| Transfer activity | **No** — dataset has no transfer data at all | N/A | N/A | N/A | **No** |
| News goal/clean-sheet/BTTS impact | **No** — dataset has no news/article data at all | N/A | N/A | N/A | **No** |

All four gated families fail at check A for the selected candidate specifically because the
candidate contains none of this data by construction (§5's core selection rationale). Had a
lineup-carrying candidate been selected instead (e.g. the rejected European Soccer Database), the
answer would still be **No** at check B — that dataset documents no availability-before-kickoff
timestamp for its lineup records, only that a lineup existed for a completed match. Per the master
prompt's own Phase 9 rule ("If ANY answer is no: DO NOT publish it as a legitimate pre-match
feature. Report it as unresolved."), every gated feature is reported here as **unresolved**, not
approximated, not defaulted, not weighted down and accepted anyway.

## 13. Historical provenance classification

Using TitanIQ's existing architecture (§ correction in item J of the repository audit — two
independent enums, `AvailabilityClassification` for structured sports data and
`NewsAvailabilityClassification` for news, both gated on `SyncTrigger.LIVE_SCHEDULED` at
`provenance.py:121` / `news_provenance.py:70`): any Kaggle-sourced structured-intelligence record
would need a `SyncTrigger` value to enter this classification path at all, and none of `BACKFILL`,
`ADMIN_MANUAL`, or any hypothetical new "Kaggle" trigger could ever satisfy `is not LIVE_SCHEDULED`
→ they would correctly and unavoidably classify as `UNKNOWN_AVAILABILITY_TIME` (structured) or the
same value (news) — exactly the master prompt's own required "HISTORICALLY_UNRESOLVED" outcome for
provenance that cannot be honestly proven. No modification to `classify_availability()` /
`classify_news_availability()` is needed, proposed, or would be acceptable to make Kaggle data
appear eligible — the existing architecture already represents this correctly with zero new code.

## 14. DatasetBuilder compatibility

`DatasetBuilder.build()` (`modules/predictions/application/dataset_builder_service.py:159`) does
**not** read raw historical data directly — it only ever reads already-resolved
`PredictionOutcome` + `Prediction.feature_snapshot` rows (§ correction, item B of the repository
audit). This means Kaggle-derived fixtures could only ever enter training the same way every other
historical fixture does today: as a normal completed `Fixture` (with real `TeamStatistics`) that
flows through the *existing* feature-calculation pipeline (`FixtureFormDifferentialCalculator`,
`FixtureExpectedGoalsCalculator`, odds-derived features) to produce a real `Prediction` with a real
`feature_snapshot`, which `OutcomeResolutionService` then resolves into a `PredictionOutcome` —
exactly the same shape as the 11 existing `scripts/backfill_*_training_data.py` scripts already use
for TitanIQ's own historical fixtures. **No change to `DatasetBuilder`, `TrainingSample`, or
`DatasetLineage` would be needed** — a Kaggle import, if pursued, would be a new *fixture-ingestion*
adapter feeding the existing pipeline, not a training-infrastructure change. This satisfies the
master prompt's "prefer adapters over changes to established training infrastructure" instruction
directly.

**Correction to a prior report**: M19's audit and M24's final verification report both state
`dataset_provenance_persisted` fails because `DatasetRepositoryPort` is "in-memory-only by design
(ADR-008)". This is now stale. `SqlAlchemyDatasetRepository`
(`modules/predictions/infrastructure/persistence/repositories.py:337-373`, table `datasets`,
created by `alembic/versions/0023_ml_platform_schema.py`) exists and has been the *production*
wiring since Milestone 20 (`apps/api/composition.py:936-943`, `build_dataset_repo()`). The gate
still correctly fails today — but because no code path has ever actually called
`DatasetRepositoryPort.upsert()` for any of these 14 markets (a workflow gap: nothing currently
triggers a real training run that would persist its built `Dataset`), not because persistence is
architecturally impossible. This does not change M24's STATE A conclusion — it corrects the
stated *reason* for one sub-check, for the record.

## 15. Preflight results (re-run fresh, not staged data)

`scripts/run_training_preflight.py --all-trained-football`, re-run today against TitanIQ's real
`dev.db` (no Kaggle data staged or imported — nothing to run preflight against yet): **0/14 READY**,
identical to every prior run this session. No staged-dataset preflight run was performed, since
§1's finding means the outcome is provably identical whether or not Kaggle data is imported.

## 16. Additional observations available

**Zero**, from Kaggle import, on the dimension that actually gates training (gated intelligence
features). Non-zero but unquantified without downloading the real file: additional historical
fixture/result/odds rows for leagues or date ranges TitanIQ's own providers have not fully
backfilled — genuinely useful for future model quality once training is unblocked by real time
passing, but not scoped or measured in this audit (would require the actual CSV, §17).

## 17. Remaining blockers / recommended next action — decision needed

Two independent, unrelated blockers exist:

1. **The provenance/time blocker (§1, unchanged by this audit)**: only real fixtures approaching
   kickoff while TitanIQ's live pipeline runs can ever produce `VERIFIED_PRE_MATCH` observations.
   No action in this task, or any Kaggle import, changes this.
2. **The fixture-matching gap (§9)**: no team-name-based matcher exists in TitanIQ's core
   reconciliation pipeline today; building one is real new engineering surface.

Given blocker 1 makes the Kaggle import's *stated purpose* (unblocking training) unachievable
regardless of data quality or volume, and blocker 2 means acquiring the data would require new
matching infrastructure the master prompt itself says should require explicit sign-off before
building — **this audit stops here, before downloading anything**, per the master prompt's own
Phase 3 instruction ("do not force a dataset into TitanIQ") and its external-API-safety section
("If Kaggle authentication or API credentials are required: STOP and ask for them").

Concretely: downloading the primary candidate's CSV requires either a Kaggle account + API token
(`kaggle.json`) for the `kaggle` CLI, or a manual browser download (which itself typically requires
a signed-in Kaggle session). Neither is available in this environment, and per the master prompt's
own rule, credentials must not be fabricated.

**The recommended next action is a decision, not further unauthorized work**: given §1's finding
that Kaggle data cannot unblock training for any of the 14 markets, is it still worth acquiring
this dataset purely for its secondary value (broader historical box-score/odds coverage,
independent of the blocked gate) — which would require (a) Kaggle credentials, and (b) building the
new fixture-matching adapter flagged in §9? Or does §1's finding mean this line of work should stop
here, with the audit itself (this document) as the deliverable?

## 18. Exact files changed

**None.** This is a pure audit — zero application files, zero migrations, zero `dev.db` writes.
One new file created: this report, `backend/docs/historical_data_expansion_audit.md`.

## 19. Test results

Not applicable — no code was written or changed this task; nothing to test.

## 20. Database safety confirmation

Row counts captured before this audit (§2) and re-verified identical at time of writing this
report: `datasets`=0, `models`=47, `predictions`=12436, `feature_values_offline`=71223,
`news_articles`=319, `news_events`=68, `intelligence_sync_runs`=47,
`intelligence_sync_checkpoints`=8, `transfers`=308, `fixtures`=6834. `dev.db` was not written to at
any point during this audit.
