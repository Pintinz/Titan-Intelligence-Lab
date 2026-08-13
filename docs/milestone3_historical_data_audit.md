# TitanIQ — Milestone 3: Initial Historical Data Audit

**Status: READ-ONLY. No production code modified. No database structures modified. Nothing deleted. No models trained. No synthetic data generated. No missing records fabricated.** Every number below is a live SELECT-query result against `backend/dev.db`, executed 2026-08-11, not a re-statement of Milestone 1/2's earlier (partly now-stale) findings.

**Read this before the sport-by-sport detail:** two of Milestone 1's conclusions are now materially out of date. Real (non-mock) fixture data for basketball and baseball exists today — a real sync clearly ran on **2026-08-10**, one day before this audit, after Milestone 1 was written. This changes the shape of Milestone 4 planning meaningfully and is the single most important correction this document makes.

---

## 1. Executive Summary

- **Football**: 1,203 fixtures (823 completed, 380 scheduled), real, well-covered. 14 of 19 seeded markets have genuinely trained Champions and a large resolved-outcome corpus — but that corpus is almost entirely backfill-script-derived, not organically served, so its point-in-time provenance is **unverified**, not disproven. 4 half-based markets are structurally blocked: football's period-score extraction was never built, so `period_scores` is null on all 823 completed fixtures.
- **Basketball**: **1,708 real fixtures now exist** (100% `api_basketball`-sourced, not mock) — a reversal of Milestone 1's finding. But everything below fixture/score level is absent: 0 players, 0 player_statistics, 0 lineups, 0 injuries, 0 standings, team_statistics covers only 3.5% of fixtures. Zero predictions have ever been generated against any of its 7 markets.
- **Baseball**: **3,923 real fixtures now exist** (100% `api_baseball`-sourced), same reversal. Even thinner downstream than basketball: team_statistics covers 1.8% of fixtures with only `{runs, hits, errors}` (no pitching/batting detail), 0 players/lineups/standings, 0 predictions ever generated.
- **Tennis**: confirmed to not exist in any form — zero database rows, zero source files, zero folders. Only appears in aspirational docs and one prior audit's requirements list.
- **Table Tennis**: fully empty (0 teams/players/fixtures) despite its 6 markets carrying a `status='production'` DB value — a status-field honesty gap worth fixing even though the live API already returns an honest "insufficient data" response.
- **News Intelligence**: still 100% `MockGeminiAdapter` output (confirmed unchanged), AND newly discovered: **zero temporal overlap** between any current news event and any fixture in the database — a 26-month gap separates the fixture data (ends 2024-06) from the news data (starts 2025-12). Classification: `NOT_TRAINABLE_DUE_TO_PROVENANCE`.
- **Structured Intelligence** (injuries/transfers/lineups): real provider-sourced data exists but lacks validity-window columns, and — newly discovered — `injuries.reported_at` appears to be a **backfilled proxy equal to fixture kickoff time**, not a genuine pre-match report timestamp, which is a specific, concrete leakage risk if wired into features naively.
- **Community Intelligence**: confirmed `NOT_CONNECTED` — zero rows, zero registered provider.
- **Weather**: confirmed absent entirely, for every sport.
- **New defect found independently by two separate audits**: `provider_ref_index.entity_id` stores hyphenated UUIDs while `fixtures.id`/`teams.id` store 32-char hex with no hyphens — any code doing a direct join between them silently returns zero rows. Worth a real code audit in Milestone 4 planning.

## 2. Sport-by-Sport Historical Coverage

| Sport | Fixtures (total / completed) | Date range | Real provider? | Teams | Players | Team stats coverage | Lineups | Injuries |
|---|---|---|---|---|---|---|---|---|
| Football | 1,203 / 823 | 2022-08-05 → 2027-05-30 | `api_football` (completed) + `football_data_org` (scheduled) | real | 0 (table empty, all sports) | 45/823 (5.5%) | 2/823 (0.24%) | 30 rows |
| Basketball | 1,708 / 1,708 | 2023-10-05 → 2024-06-18 | `api_basketball`, 100% real | 50, real | 0 | 60/1,708 (3.5%, via `matches` join) | 0 | 0 |
| Baseball | 3,923 / 3,913 | 2023-02-23 → 2023-11-05 | `api_baseball`, 100% real | 48, real | 0 | 70/3,923 (1.8%) | 0 | 0 |
| Tennis | 0 | — | none exists | 0 | 0 | — | — | — |
| Table Tennis | 0 | — | none (0 rows, not even mock-persisted) | 0 | 0 | — | — | — |

`player_statistics` and `rankings` are empty **across every sport**, not just the thin ones — this is a platform-wide gap, not a per-sport one.

## 3. Market-by-Market Training Readiness Matrix

Taxonomy applied strictly — a table existing is not evidence of readiness (per the audit's own governing rule).

| Market group | Classification | Why |
|---|---|---|
| Football: 14 markets with a real trained Champion (`match_winner`, `both_teams_to_score`, 5× `total_goals_over_under*`, `home/away_team_total_goals`, `correct_score`, `home/away_clean_sheet`, `home/away_win_to_nil`) | **VALIDATION_READY** — not `PRODUCTION_READY` by this audit's strict bar | Currently serving live in production, real resolved-outcome volume (654–888 per market) — but the outcome corpus is backfill-script-derived with unverified pre-kickoff feature provenance (§13), and training used a random shuffle split, not time-based (Milestone 2 finding, unchanged). Cannot be certified `PRODUCTION_READY` until both are re-audited/fixed. |
| Football: 4 half-based markets (`first_half_winner`, `second_half_winner`, `first_half_goals`, `first_half_both_teams_to_score`) | **BLOCKED_BY_FEATURES** | 0 resolved outcomes each, despite 64–68 predictions logged. Root cause confirmed: `period_scores` is null on all 823 completed football fixtures — football's provider adapter never extracts half-scores (unlike basketball/baseball, which extract quarter/inning scores). This is a missing-capability gap, not a volume gap — cheap to close once flagged. |
| `football.match_result` | **LEGACY** | Deprecated, superseded by `match_winner`, correctly retired. |
| Basketball: 6 match-level markets (`moneyline`, `point_spread`, `game_total_points`, `team_total_points`, `first_half_winner`, `race_to_20_points`) | **DATA_AVAILABLE**, not yet `FEATURE_READY` | Real fixture/score volume is now strong (1,708), but `team_statistics` covers only 3.5% and no player/lineup/injury data exists at all. `first_half_winner` has a genuine upside here: basketball's `period_scores` is 100% populated (quarter-level), so it's derivable in principle — unlike football's equivalent, which is fully blocked. |
| `basketball.player_points_prop` | **INSUFFICIENT_DATA** | Categorically blocked — 0 basketball players exist in the database at all, not just thin coverage. |
| Baseball: 5 match-level markets (`moneyline`, `run_line`, `total_runs`, `team_total_runs`, `first_five_innings_winner`) | **DATA_AVAILABLE**, not yet `FEATURE_READY` | Same shape as basketball, thinner: `team_statistics` covers 1.8% with only `{runs,hits,errors}`. `first_five_innings_winner` has the same positive upside as basketball's half-winner — baseball's `period_scores` is 100% populated (inning-level). |
| `baseball.pitcher_strikeouts_prop` | **INSUFFICIENT_DATA** | 0 baseball players exist; no pitching-specific stat fields exist anywhere in the schema's current data. |
| All 6 tennis (proposed) markets | **Below `CATALOG_ONLY`** — no status in the required taxonomy cleanly fits "zero catalog entries, zero code, zero data." Closest is `INSUFFICIENT_DATA`, but that undersells how early-stage this is. | No markets are even seeded; nothing exists to classify yet. |
| All 6 table_tennis markets | **CATALOG_ONLY** | Seeded (DB `status='production'`, worth flagging as a status-field mismatch — see §8), 0 real fixtures/teams/players, 0 trained Champions, 0 predictions. |

## 4. Data Volume

| Data type | Football | Basketball | Baseball |
|---|---|---|---|
| Fixtures | 1,203 | 1,708 | 3,923 |
| Completed fixtures | 823 | 1,708 | 3,913 |
| Team-statistics rows | 90 | 120 | 140 |
| Player-statistics rows | 0 | 0 | 0 |
| Lineup rows | 4 (football only, of 4 total in DB) | 0 | 0 |
| Injury rows | 30 (all football) | 0 | 0 |
| Standings rows | 97 | 0 | 0 |
| Predictions logged | 12,426 (19 markets) | 0 | 0 |
| Resolved outcomes | 11,183 | 0 | 0 |

News: 146 articles, 50 events, 49 impact scores, 3 sources — flat across all sports (the intelligence pipeline is sport-agnostic and currently produces essentially football-flavored mock content regardless).

## 5. Data Completeness

- Football team_statistics: **5.5%** of completed fixtures.
- Football lineups: **0.24%** of completed fixtures.
- Basketball team_statistics: **3.5%** of fixtures (via the `matches` join — 1,648 of 1,708 fixtures have scores/period_scores on the `fixtures` row directly but no `matches` record at all, so no box-score linkage).
- Baseball team_statistics: **1.8%** of fixtures.
- Injuries/lineups/standings/rankings/players: **0%** for basketball and baseball across the board.
- News-to-fixture temporal overlap: **0%** — confirmed by a direct join at both ±1 day and −3/+10 day windows, zero matches.

## 6. Missing Features

- **Football**: `period_scores` (half-level) — never extracted, blocking 4 markets. `player_statistics` and `rankings` entirely empty.
- **Basketball/Baseball**: player-level statistics, lineups, injuries, standings — all absent. Baseball additionally has no pitching/batting-split stats even in its thin team_statistics.
- **All sports**: no structured-context features wired into any model yet (confirmed unchanged from Milestone 2 — this is a code gap, not a data gap, since raw injury/transfer data does exist for football).
- **Tennis**: no feature engineering possible — no data exists to engineer from.

## 7. Missing Outcomes

- Football: 4 half-based markets, 0/64–68 resolved (structural, see §3).
- Basketball, Baseball: 0/0 for every market — no `Prediction`/`PredictionOutcome` rows have ever been created for either sport.
- Table Tennis: 0/0 for every market, same reason.

## 8. Data Quality Problems

1. **`provider_ref_index` UUID-format mismatch** (found independently by both the football and basketball audits): `entity_id` is stored as a hyphenated UUID (`31e863dc-96b3-...`) while `fixtures.id`/`teams.id` are stored as 32-char hex with no hyphens. Any direct-equality join between these silently returns zero rows. Real per-fixture provenance for football had to be read from `fixtures.provider_ref` JSON instead — this bug may be masking other broken joins elsewhere in the codebase and is worth a dedicated Milestone-4 code sweep.
2. **`injuries.reported_at` appears to be a backfilled proxy equal to fixture kickoff time**, not a genuine report timestamp — confirmed by exact-match sampling (a Newcastle player's `reported_at` landed on the exact second of a real Newcastle fixture kickoff). If used as a "known before kickoff" signal without further audit, this risks encoding same-day/post-hoc knowledge as if it were pre-match.
3. **`transfers.transfer_type` has mojibake/encoding-corrupted currency text** in several rows (e.g. a replacement character where a currency symbol should be) — a real, if minor, data-quality defect.
4. **`coaching_staff` has the right schema for tracking manager transitions (`valid_from`/`valid_to`) but has never actually recorded one** — all 5 rows are single, un-transitioned snapshots from one ingestion moment. A "manager change" feature built on this today would silently never fire.
5. **`lineups` has only 4 rows total**, and their `created_at` (2026, today) gives no way to distinguish "confirmed shortly before a 2023 kickoff" from "reconstructed after the fact" — no kickoff-relative timestamp exists on the table at all.
6. No duplicate fixtures, duplicate teams, or duplicate provider-ref collisions were found in football, basketball, or baseball — this part of the data is clean.
7. No invalid/null timestamps found in any fixture table across the three real sports.

## 9. News Intelligence Historical Readiness

**Classification: `NOT_TRAINABLE_DUE_TO_PROVENANCE`.**

- 50 `news_events`/49 `impact_scores` rows, confirmed still 100% `MockGeminiAdapter` output: only 4 distinct confidence values (0.5/0.6/0.65/0.7) across 50 rows, only 6 distinct canned summary strings, and literal `"mock_player"`/`"mock_team"`/`"mock_coach"`/`"mock_venue"` placeholder strings present in nearly every `affected_entity_refs` array.
- A real, active Gemini credential is registered (confirmed) — it simply wasn't the source of this dataset, which came from a one-off backfill script (`backfill_news_event_extraction.py`) using the mock adapter instead.
- Ingestion is batch/backfilled, not continuous: `published_at` → `fetched_at` gaps range from under 2 hours to **234 days** for individual real articles.
- **New finding, more severe than the mock-content issue alone**: `news_events.occurred_at` spans 2025-12-10 → 2026-08-07, while `fixtures` has a completed-fixture window of 2022-08-05 → 2024-06-18 and a scheduled-fixture window of 2026-08-21 → 2027-05-30 — a **26-month gap with zero fixtures** sits exactly where all the current news data lives. A direct join found 0 matches at any reasonable window. Even if the mock-content issue were fixed today, there is currently no fixture for any existing news event to inform.

## 10. Structured Injury/Transfer/Lineup Readiness

**Classification: real data, `NOT READY` for point-in-time historical use without schema changes; usable for "latest known state" live serving already.**

- Real schemas confirmed via `PRAGMA table_info`: `injuries` and `transfers` each have a single point-in-time timestamp (`reported_at`, `effective_date`) with **no `effective_until`/validity-window column** — only `coaching_staff` has real `valid_from`/`valid_to`.
- Data content is real and specific (real player names, real injury reasons like "Hamstring Injury", "Achilles Tendon Injury"; real transfer fees and types) — not synthetic placeholder text.
- 30 injuries, 0 suspensions, 308 transfers, 4 lineups, 5 coaching_staff rows.
- The §8 finding (injuries.reported_at as a kickoff-time proxy) is the single most important caveat here — it means even the one timestamp this data does have may not be trustworthy as-is for a "was this known before kickoff" check.
- Coverage overlap with real fixtures exists (sampled injuries do line up with real nearby fixtures) but is thin relative to fixture volume (30 injuries against 6,834 total fixtures across all sports).

## 11. Community Intelligence Readiness

**Classification: `NOT_CONNECTED`.**

`community_posts`=0, `community_topics`=0. No community/social-platform provider is registered in the `providers` table (7 registered providers, all sports-data/LLM, none social). `CommunityIngestionService` is constructed with `providers={}` at its one real call site. The only implementation, `MockCommunityProvider`, is never referenced by production wiring — confirmed unchanged from Milestone 1.

## 12. Weather Readiness

**Classification: does not exist, for any sport.**

Zero weather columns on `venues` or `fixtures`. Zero weather-fetching code in any provider adapter. The only "weather" hits anywhere in the codebase are a `NewsEventType.WEATHER_REPORT` news-text classification label, which is explicitly and intentionally never wired to any feature (a test asserts this directly) — this is a text-classification category name, not meteorological data, and should not be confused with one.

## 13. Temporal Validity / Leakage Readiness

Re-confirming Milestone 2's finding with concrete new evidence: **the architecture cannot currently answer "what was known at time T" for any data type.**

| Data type | Can reconstruct point-in-time state? | Evidence |
|---|---|---|
| Sports statistics | **No** | `feature_values_offline` has no as-of query method (Milestone 1/2 finding, unchanged) |
| News | **No** | Zero temporal overlap with fixtures at all (§9) — the question is currently unanswerable for lack of overlapping data, on top of the missing query capability |
| Injuries | **Partially, with a specific known defect** | Only one timestamp exists, and it appears to be a kickoff-time proxy in sampled cases (§8, §10) — not safe to trust today |
| Transfers | **No** | Single `effective_date`, no distinct "announced" vs. "took effect" timestamps |
| Lineups | **No** | No kickoff-relative timestamp at all; only ingestion time exists |
| Community | **N/A** | No data exists to test against |
| Weather | **N/A** | No data exists to test against |

This is the single highest-priority engineering gap identified across Milestones 1–3, consistent with the approved direction naming it non-negotiable.

## 14. Provider Coverage

| Provider | Role | Status |
|---|---|---|
| `api_football` | Primary, football completed fixtures | Real, active |
| `football_data_org` | Supplementary, football scheduled fixtures | Real, active |
| `thesportsdb` | Supplementary, football team cross-referencing only (24 teams) | Real, active, correctly scoped non-authoritative |
| `api_basketball` | Primary, basketball fixtures/teams | Real, active — **now confirmed populated**, reversing Milestone 1 |
| `api_baseball` | Primary, baseball fixtures/teams | Real, active — **now confirmed populated**, reversing Milestone 1 |
| `gemini` | News/community NLP extraction | Real, active credential, **not currently the source of any data in the DB** |
| (none registered) | Tennis | No provider selected or integrated |
| (none registered) | Community/social | No provider selected or integrated |
| (none registered) | Weather | No provider selected or integrated |

## 15. Training Eligibility

- **Football**: eligible for continued live serving on its 14 real-Champion markets, with the leakage/split-strategy caveats in §3 documented as open risk, not resolved. Eligible for a scoped fix (half-score extraction) to unblock its 4 blocked markets.
- **Basketball / Baseball**: **not eligible** to begin real training yet — fixture/score volume is now genuinely strong, but zero players, lineups, injuries, or standings exist, and team-statistics coverage is in the low single digits. This is closer than Milestone 1 assumed, but still a real gap, not a formality.
- **Tennis**: not eligible — no provider, no data, no code. This requires a product/procurement decision before any further audit is even possible.
- **Table Tennis**: not applicable — legacy, correctly out of scope.
- **News**: not eligible — mock content and zero temporal overlap with any fixture.
- **Structured intelligence**: eligible for **live** "latest known state" use once wired (per Milestone 2 §1.4's recommendation, which still stands); **not** eligible for historical/backtest use until validity-window columns exist and the `reported_at` proxy issue is resolved.
- **Community**: not eligible — not connected.
- **Weather**: not eligible — does not exist.

## 16. Blocked Markets

- `football.first_half_winner`, `.second_half_winner`, `.first_half_goals`, `.first_half_both_teams_to_score` — `BLOCKED_BY_FEATURES` (period_scores never extracted for football).
- `basketball.player_points_prop` — `INSUFFICIENT_DATA` (zero players).
- `baseball.pitcher_strikeouts_prop` — `INSUFFICIENT_DATA` (zero players, no pitching stats).
- All 6 `table_tennis.*` markets — `CATALOG_ONLY` (zero real data of any kind).
- All 6 proposed `tennis.*` markets — pre-catalog, nothing seeded.

## 17. Recommended Data Acquisition Priorities (ranked)

1. **Basketball/baseball player-level statistics, lineups, injuries, and standings.** Fixture-level data is now unexpectedly strong for both sports — this is the highest-leverage acquisition, since it's the only thing standing between "real fixtures exist" and "match-level markets are feature-ready."
2. **Football period-score (half-level) extraction.** Cheap relative to everything else on this list — it's an adapter capability gap, not a new provider, and unblocks 4 already-seeded, already-live markets.
3. **Tennis provider selection and historical-data acquisition.** The largest single lift on this list, and a product decision, not an engineering one — flagged, not solved, here.
4. **Real, continuously-scheduled news ingestion with actual temporal coverage of the fixture window.** Today's news data is both mock and 26 months detached from any fixture — fixing the mock-content issue alone would not make it useful without also closing the date-range gap.
5. **Community provider selection.** Lowest priority given its explicitly supporting-only role, but still a prerequisite for the ablation-testing framework (Milestone 2 §1.6) to ever run a real "with community" arm.

## 18. Recommended Next Engineering Priorities (code, not data)

1. **Fix the `provider_ref_index` UUID-format join bug.** Found independently twice in this audit; likely affects other code paths beyond what was sampled here — worth a dedicated sweep.
2. **Build point-in-time query capability** (Milestone 2 §1.1) — now more urgent given the concrete `injuries.reported_at` proxy-timestamp finding, which is exactly the kind of silent leakage this capability is meant to catch.
3. **Add `effective_from`/`effective_until` to `injuries`, `transfers`, `lineups`**, and specifically audit whether `injuries.reported_at` can be replaced with a genuine report timestamp or needs a documented caveat if it can't.
4. **Fix the football-market DB `status` field for the 5 placeholder-heuristic markets and 6 table_tennis markets** so the raw field matches the honest behavior the live API already returns (Milestone 2 §1.8, restated here because §3/§16 make the scale of the mismatch concrete).
5. **Investigate whether the 14 real football Champions' training corpus is organically-served or entirely backfill-derived** — §3's finding that the resolved-outcome volume almost exactly tracks completed-fixture count per market is a strong signal it's the latter, which the temporal-validity work in #2 should be able to confirm or rule out directly once built.

## 19. Risks

- The entire currently-"trained" football Champion set may be trained on backfill-derived rows with unverified pre-kickoff feature provenance — not confirmed broken, but not confirmed clean either, and currently unfalsifiable without #2/#5 above.
- `injuries.reported_at` silently behaving as a kickoff-time proxy is a concrete leakage vector if Milestone 2's structured-feature wiring (§1.4) is built before this is resolved.
- The `provider_ref_index` join bug may be silently causing zero-result joins elsewhere in the codebase beyond what this audit sampled.
- Market DB `status='production'` on markets with zero real Champion/data (5 football, all 6 table_tennis) is a reporting/trust risk if that raw field is ever surfaced to a non-technical stakeholder without translation, even though the live API behavior is already honest.
- `coaching_staff`'s never-exercised transition tracking means a "manager change" feature, if built now, would silently always report "no change" — a false-negative risk baked in from day one if not caught before building on top of it.
- Mojibake in `transfers.transfer_type` could break naive downstream text parsing if that field is ever consumed programmatically rather than just displayed.

## 20. Final Go/No-Go Assessment

**No-Go for any new model training, on any sport, right now.** This is consistent with the approved direction's instruction not to fabricate training readiness.

- **Football**: current production markets may continue serving, but carry a documented, unresolved provenance risk — recommend treating this as a known-risk-accepted state, not a clean bill of health, until §18 items #2 and #5 are done.
- **Basketball/Baseball**: **No-Go**, but meaningfully closer than Milestone 1 assumed — the fixture-level foundation genuinely exists now; the remaining gap is specifically players/lineups/injuries/standings, not raw match data.
- **Tennis**: **No-Go**, blocked on a provider decision outside this audit's authority.
- **Table Tennis**: **No-Go** / not applicable, correctly legacy.
- **News/Community/Weather-based features**: **No-Go** for all three, for different reasons (provenance+coverage gap; not connected; doesn't exist).

**Recommended scope for whatever comes next: the five items in §18 (all cheap, well-scoped, code-only fixes) — not new training, not new sport buildout, not news/community wiring — until this audit's own findings are acted on.**

---

**STOP — per the required output format.** This is the complete Milestone 3 report. Nothing has been implemented, modified, or fabricated. Waiting for explicit approval before Milestone 4.
