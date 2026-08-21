# POST-M24 Master Data Fabric — Phase 7 Verification Report

## Current-Season Fixture & Live Data Enablement

**Date:** 2026-08-15
**Scope:** Read-only current-season audit across all four sports, followed by a real attempt to
register genuine current-season basketball/baseball fixtures via the existing, unmodified
`SyncOrchestrator.sync_fixtures` pipeline — the same pipeline football's own 380 real future
fixtures already came from. No fabricated fixtures, odds, news, or observations. No training, no
Champion changes, no calibration.

---

## 1. Executive Summary

Football already has a genuine, working current-season pipeline — **380 real future fixtures**,
already reconciled, spanning out to 2027-05-30. Basketball and baseball had **zero** future
fixtures before this phase.

This phase attempted the real, minimal, evidence-based fix: reconcile a genuine current season
(MLB "2026", NBA "2026-2027") against the real competitions already in `dev.db`, then call the
same `sync_fixtures` method football's pipeline already uses. Both real provider calls returned a
**definitive, explicit rejection**: *"Free plans do not have access to this season, try from 2022
to 2024."* This is the single most important finding of this phase — a genuine, hard, plan-tier
restriction on this environment's `api_basketball`/`api_baseball` credentials, not a code defect,
not missing architecture, and not something more engineering can route around. It also explains,
retroactively, exactly why every basketball/baseball fixture already in `dev.db` stops at
2023/2024: this account has never been able to fetch beyond that window, for any sport, at any
phase of this initiative.

Given that, basketball and baseball **remain without current-season fixtures**, and every
downstream consumer (odds, news, structured intelligence, VERIFIED_PRE_MATCH accumulation) has
nothing new to attach to for those two sports. Football's own pipeline required no new work — it
was verified working, not rebuilt. Table tennis remains UNSUPPORTED, unchanged. Two real season
rows (MLB "2026", NBA "2026-2027") were reconciled and preserved as an honest record of what was
attempted, correctly holding zero fixtures.

---

## 2. Step 1 — Read-Only Current-Season Audit (Matrix)

| Sport | League | Competition | Season(s) registered | Latest historical fixture | Earliest upcoming fixture | Provider | Fixture count |
|---|---|---|---|---|---|---|---|
| Football | Premier League | `a2721390-...` | 2021, 2022, 2023, 2025, 2026 | 2027-05-30 (future) | real, within existing 380 | `api_football` | 1,203 |
| Football | DFB-Pokal | `30d4290d-...` | 2023, 2024, 2025, 2026 | (included above) | (included above) | `api_football` | (included above) |
| Football | Premier League (2nd row, `football_data_org` fallback source) | `47dc369f-...` | 2025 | — | — | `football_data_org` | — |
| Basketball | NBA | `353cb635-...` | 2025-2026 (pre-existing) + **2026-2027 (new this phase, 0 fixtures)** | 2024-06-18 | **none** | `api_basketball` | 1,708 |
| Basketball | EuroLeague | `808fb625-...` | 2025 | — | — | `api_basketball` | — |
| Baseball | MLB | `ac29e525-...` | 2023 (pre-existing) + **2026 (new this phase, 0 fixtures)** | 2023-11-05 | **none** | `api_baseball` | 3,923 |
| Baseball | NPB | `c159877d-...` | 2023 | — | — | `api_baseball` | — |
| Table Tennis | — | — | none registered | — | — | none | 0 |

Football: **380 future fixtures already exist**, real, already reconciled — no read-only finding
required further action. Basketball/baseball: **0 future fixtures**, confirmed structurally
unobtainable this phase (§4). Table tennis: **0 fixtures of any kind**, confirmed UNSUPPORTED
(§9) — no provider adapter exists for it anywhere in this codebase.

---

## 3. Step 2 — Provider Capability Audit

Reused Phase 3/5B/6's own established matrix; no new capability discovery was needed beyond
confirming plan-tier limits (§4):

| Provider | Current-season fixtures | Historical fixtures | League/competition/season endpoints | Rate limits |
|---|---|---|---|---|
| `api_football` | Yes (real, already working) | Yes | Yes | Free tier, already respected by existing cache/quota layer |
| `api_basketball` | **No — plan restricted to 2022-2024** | Yes (2022-2024 only) | Yes | Free tier explicitly gates season access, confirmed via real rejection message |
| `api_baseball` | **No — plan restricted to 2022-2024** | Yes (2022-2024 only) | Yes | Same restriction, same real rejection message |
| `football_data_org` | Fallback/secondary for football only | Yes (football only) | Yes | Free tier, 10 req/min (existing, unchanged) |
| `thesportsdb` | Supplementary, football only | Limited | Yes | Existing, unchanged |

No provider was assumed to serve every sport — confirmed directly against `composition.py`'s
`real_adapters` wiring (`football`→`ApiFootballAdapter`, `basketball`→`ApiBasketballAdapter`,
`baseball`→`ApiBaseballAdapter`) and each adapter's actual methods, exactly as Phase 6 already
established.

---

## 4. Real Current-Season Registration Attempt (What Was Actually Called)

Reused, unmodified: `EntityReconciliationService.reconcile_season` and `SyncOrchestrator
.sync_fixtures` — the exact same methods that already produced football's 380 real future
fixtures. No new ingestion framework was built, per the phase's own explicit instruction.

1. **Baseball (MLB)**: reconciled a real season row (`label="2026"`, `api_baseball` provider ref
   `"1"`, TitanIQ's own already-existing MLB competition). Called `sync_fixtures("baseball", "1",
   "2026", season_id, now, trigger=LIVE_SCHEDULED)`.
   **Result**: `SyncStatus.FAILED`, `records_fetched=0`. Real error, preserved verbatim in
   `sync_runs.error_message`: *`api_baseball request to /games rejected by provider: {'plan':
   'Free plans do not have access to this season, try from 2022 to 2024.'}`*

2. **Basketball (NBA)**: reconciled a real season row (`label="2026-2027"`, `api_basketball`
   provider ref `"12"`, TitanIQ's own already-existing NBA competition). Called
   `sync_fixtures("basketball", "12", "2026-2027", season_id, now, trigger=LIVE_SCHEDULED)`.
   **Result**: identical `SyncStatus.FAILED`, identical rejection message (basketball-specific
   endpoint, same plan-tier gate).

**External API calls this phase: 2** (one per sport, both against `/games`, both genuinely
rejected by the provider's own plan enforcement — not empty-but-accepted responses, an explicit
403-equivalent rejection). No odds call was made this phase (§8 — the phase's own condition for
one, "only if fixtures genuinely exist," was never met). **Gemini calls this phase: 0.**

**Why this is not treated as an architecture failure**: the rejection is the provider's own
account-tier enforcement, identical in shape to the free-tier gates already documented for
`football_data_org` (10 req/min) and consistent with Phase 6's own finding that this account's
plan has real, hard limits. `SyncOrchestrator._fail` preserved the exact provider message rather
than swallowing or generalizing it — confirmed by direct `sync_runs` query and now covered by a
new deterministic test (§11).

---

## 5. Step 3 — Sport/League/Competition/Season Isolation

Confirmed via source read (not a new mechanism — already existed): `SyncOrchestrator._run_sync`'s
checkpoint and distributed lock are keyed by `(sport_code, entity_kind, scope_key)` where
`scope_key = f"{competition_ref}:{season_label}"`. This means a basketball/NBA/2026 request and a
basketball/NCAA/2025 request can never collide, share a checkpoint, or be treated as "already
synced" by one another — genuine, pre-existing, three-dimension isolation. A new deterministic
test (§11) proves two different seasons on the exact same competition (`"39:2024"` vs.
`"39:2026"`) produce distinct scope keys and independent sync runs.

---

## 6. Steps 4-5 — Fixture Registration Path & Cache/Quota/Circuit Breaker

No new registration path was built — `sync_fixtures` already routes through `SportsProviderRouter
.fetch_fixtures`, which is already cache/quota/circuit-breaker-wrapped (confirmed in Phase 6's own
audit of this router). Both real calls this phase went through that exact path — neither bypassed
the router nor called an HTTP client directly. **CACHE: PASS** (pre-existing, unmodified,
correctly invoked). **QUOTA: PASS** (same). **CIRCUIT BREAKER: NOT EXERCISED** (a single
provider-level rejection is not a circuit-breaker-triggering failure pattern — no retry storm
occurred, nothing to trip).

Reconciliation reused `EntityReconciliationService` and `provider_ref_index` exactly as they
already exist — no second fixture-matching engine was built. Since neither call returned any
fixture, reconciliation itself was never exercised against real basketball/baseball fixture
records this phase (nothing to reconcile) — **FIXTURE RECONCILIATION: PASS** in the sense that
the correct, existing path was used and no incorrect/duplicate fixture was ever created.
**DUPLICATE PREVENTION: PASS** (unexercised for basketball/baseball this phase, but unchanged and
already proven for football's 380 fixtures).

---

## 7. Steps 6-7 — Fixture Window and `started_at` Semantics

The existing accumulation window (whatever T-minus-N-days logic already governs "upcoming" vs.
"live" vs. "completed" fixture classification) was **not modified** — no evidence of a defect in
it was found, and the phase's own instruction is explicit not to touch it without one. Confirmed
directly: `EntityReconciliationService.reconcile_fixture` never sets `started_at` — that field
belongs to the separate `Match` entity, created on first use via `get_or_create_match`
(Phase 5A's own fix), and is only ever populated from a fixture's real `scheduled_at` — never
backdated to "now" for a future fixture. This was **not changed** this phase; it was verified
unchanged and correct, consistent with the Phase 5A fix already in place. No basketball/baseball
fixture was created this phase to test this against directly (§4), so this is a source-level
verification, not a live one, for those two sports — football's own 380 fixtures already exercise
this path correctly (pre-existing, unmodified).

---

## 8. Steps 8-10 — Per-Sport Results

**Basketball (Step 8)**: current-season fixtures **cannot** be retrieved — confirmed via a real,
direct call (§4), not assumed. No fixture was registered; none was fabricated. `basketball`
remains at 1,708 fixtures, 0 future.

**Baseball (Step 9)**: identical outcome, identical real evidence. `baseball` remains at 3,923
fixtures, 0 future.

**Football (Step 10)**: verified independently, not assumed working because basketball/baseball's
pipeline shares code with it. Confirmed via direct query: 380 real future fixtures already exist,
current league/competition/season rows are real and already reconciled, `scheduled_at` is
populated on every one. No new provider call was made for football this phase — none was needed;
the existing pipeline already demonstrably works, and re-calling it would have been an
unnecessary, quota-consuming duplicate request the phase's own free-tier rule prohibits.

---

## 9. Step 11 — Table Tennis

Re-verified: **UNSUPPORTED**, unchanged. `table_tennis` has 0 fixtures of any kind and no
registered provider adapter anywhere in `composition.py`'s `real_adapters`/`mock_adapters` wiring.
No fake, mock, or synthetic fixture was created.

---

## 10. Step 12 — Odds Verification

**Not performed this phase.** The phase's own explicit condition — "Once genuine current-season
basketball/baseball fixtures exist... Only if fixtures genuinely exist and are within provider
retention" — was never met (§4, §8). Making an additional real `/odds` call against a fixture that
doesn't exist would have been pointless and would have burned quota without evidence to gain,
violating the phase's own free-tier discipline. Phase 6's own two `/odds` calls (against the
newest fixtures then available) remain the most recent real evidence on that endpoint; nothing new
was learned or needed here. `market_lines` remains at 0 rows.

---

## 11. Testing

**2 new tests, both passing**, added to the existing `test_sync_orchestrator.py` (no new test file
was needed — no new production module was written this phase, only existing methods were invoked
against real data):

- `test_sync_fixtures_scope_key_isolates_by_season_never_sharing_a_checkpoint` — proves two
  different seasons on the identical competition produce distinct `scope_key`s and independent
  sync runs (`"39:2024"` vs. `"39:2026"`), directly validating §5's isolation claim.
- `test_sync_fixtures_surfaces_a_real_provider_rejection_as_a_failed_run` — reproduces the exact
  real plan-tier rejection message this phase hit live, asserting it surfaces as a genuine
  `SyncStatus.FAILED` run with the verbatim provider message preserved, never silently swallowed
  or misreported as an empty success.

Targeted run: **52 passed, 0 failed** (`test_sync_orchestrator.py` in full, including the two new
tests).

Full backend suite: see §14.

---

## 12. Steps 13-15 — News, Structured Intelligence, and Provenance

**News eligibility**: football's existing 380 future fixtures are already eligible for
`sync_scheduled_news` under the existing, unmodified pipeline — no new fixture triggers this
newly; nothing was rebuilt. Basketball/baseball have no new fixtures to become eligible (§8), so
this remains **NOT EXERCISED** for those two sports this phase — an honest, expected result, not a
failure.

**Structured intelligence**: identical reasoning — football's existing fixtures were already
eligible before this phase; basketball/baseball have nothing new. **NOT EXERCISED** for
basketball/baseball.

**Provenance**: unchanged. The two new (empty) season reconciliations used `SyncTrigger
.LIVE_SCHEDULED`, correctly matching "current scheduled data" per the phase's own instruction —
verified via direct `sync_runs.trigger` inspection (`'live_scheduled'` on both real rows). No
provenance gate was weakened. Registering a fixture — had one been returned — would **not** have
automatically classified any of its features as `VERIFIED_PRE_MATCH`; that gate remains untouched
and was never at risk of being bypassed, since no fixture was ever returned to test it against.

---

## 13. Steps 16-17 — Data Accumulation Readiness & Training Preflight

**VERIFIED_PRE_MATCH observations: 0** (unchanged from before this phase) — no new
basketball/baseball fixture exists to accumulate one against, and this phase created none.

**Training Preflight** — run as a genuine read-only diagnostic (`TrainingPreflightService.check`,
no training, no persistence side effects) against three representative markets:

| Market | Ready | Key failing checks |
|---|---|---|
| `basketball.q1_winner` (Phase 5B's newest market) | **NOT READY** | `sufficient_labeled_observations` (0 of 30 minimum), `temporal_reference_present`, `temporal_split_valid`, `training_inference_feature_parity`, `required_feature_coverage_acceptable`, `dataset_provenance_persisted` |
| `basketball.moneyline` | **NOT READY** | Same shape — 0 labeled samples; three required features (including the Phase 6-relevant `basketball.market.overround`) show 0.0% coverage |
| `football.match_winner` (already has a real, live-serving Champion) | **NOT READY** | Notably, even football's own trained, Champion-serving market fails preflight — 658 labeled samples exist (well above the 30 minimum) and pass most checks, but `training_inference_feature_parity` fails (4 lineup-continuity/transfer-activity features required at inference are absent from every training sample) and `dataset_provenance_persisted` fails (the dataset repository is documented in-memory-only, a pre-existing, unrelated architectural note — ADR-008) |

This confirms readiness is **unchanged by this phase's work**, exactly as expected — the phase
never claimed or attempted to move it. Football's own preflight gap (feature parity,
dataset-provenance persistence) is pre-existing and unrelated to current-season fixture
availability; it is not a Phase 7 defect and was not touched.

---

## 14. Full Regression Suite Result

**2,417 passed, 58 skipped, 0 failed** (637.40s / 10:37). Baseline entering this phase was 2,415
passed / 58 skipped / 0 failed — a delta of **+2 passed, 0 skipped change, 0 failed**, exactly
matching this phase's 2 new tests. Zero regressions.

---

## 15. Database Safety — Before/After Delta

| Table | Before | After | Delta | Explanation |
|---|---|---|---|---|
| `seasons` | 18 | 20 | **+2** | The two real, empty season rows reconciled this phase (MLB "2026", NBA "2026-2027") — honest records of a real, evidence-yielding attempt, not fabricated data. |
| `sync_runs` | (pre-existing) | +2 | **+2** | The two real FAILED runs, provider rejection preserved verbatim. |
| `sync_checkpoints` | 201 | 203 | **+2** | One checkpoint per new `(sport_code, entity_kind, scope_key)` combination — real isolation, per §5. |
| `provider_ref_index` | 7,529 | 7,531 | **+2** | Synthetic season ref-index entries from `reconcile_season`, same mechanism every existing season row already uses. |
| `fixtures` | 6,834 | 6,834 | 0 | **No fixture was created** — neither provider call returned any record. |
| `matches` / `teams` / `competitions` | unchanged | unchanged | 0 | Unchanged. |
| `market_lines` | 0 | 0 | 0 | Unchanged — no odds call was made this phase (§10). |
| `news_articles` / `news_events` / `intelligence_sync_runs` / `intelligence_sync_checkpoints` | unchanged | unchanged | 0 | Unchanged — no new fixture became eligible (§12). |
| `prediction_markets` | 43 | 43 | 0 | Unchanged this phase (Phase 6's own correction already brought this to 43). |
| `predictions` / `prediction_outcomes` | unchanged | unchanged | 0 | Unchanged — `TrainingPreflightService.check` is read-only by design; confirmed no side effects. |
| `datasets` | 0 | 0 | 0 | Unchanged — preflight's dataset build is in-memory only (ADR-008), never persisted. |
| `models` (Champion) | 19 | 19 | 0 | **No Champion was created, modified, or promoted.** |
| `models` (candidate/retired) | 14 / 14 | 14 / 14 | 0 | Unchanged. |
| `calibration_reports` | 0 | 0 | 0 | Unchanged. |

No unexpected table (`predictions`, `prediction_outcomes`, `datasets`, `models`,
`calibration_reports`) was touched. Every delta is exactly the two real, honest, evidence-yielding
season-reconciliation attempts.

---

## 16. Remaining Blockers and Recommended Next Phase

**Remaining blocker (single, hard root cause)**: this environment's `api_basketball`/
`api_baseball` credentials are on a plan explicitly restricted to historical seasons 2022-2024.
Current-season basketball/baseball data — fixtures, odds, or anything downstream of fixtures — is
**structurally unobtainable** with this account tier, confirmed by the provider's own explicit
rejection message, not inferred. No further engineering on TitanIQ's side changes this; the
canonical architecture (schema, resolver, cache/quota, reconciliation, isolation) is all real,
tested, and ready to consume real data the moment a plan upgrade or a different provider is
authorized.

Football requires no further work — its current-season pipeline already works and was verified,
not touched.

**Recommended next phase**: either (a) authorize a plan upgrade or an alternate current-season
basketball/baseball data source, at which point the exact same `sync_fixtures` call this phase
already proved correct would immediately start registering real fixtures with zero further code
changes, or (b) proceed with an **EXPLICIT TRAINING READINESS REVIEW** focused specifically on
football, whose own preflight gap (`training_inference_feature_parity`,
`dataset_provenance_persisted`) is real, independent of current-season fixture availability, and
was surfaced as read-only diagnostic evidence this phase (§13).

---

**STOP COMPLETELY. DO NOT PROCEED TO TRAINING OR ANY SUBSEQUENT PHASE WITHOUT EXPLICIT
AUTHORIZATION.**
