# Phase 2 — Entity Reconciliation Root-Cause + Safe Synchronization Recovery

**Date:** 2026-08-18

## 1. Phase 1 baseline

Phase 1 recovered half-time data and bootstrapped real Champions for 4 football markets
(`first_half_winner`, `second_half_winner`, `first_half_goals`, `first_half_both_teams_to_score`)
but reported that `EntityReconciliationService.reconcile_fixture` "hung indefinitely" on real
fixture data, and worked around it with a narrower direct-update script rather than the standing
`SyncOrchestrator.sync_fixtures` path. That conclusion was independently re-verified in this
phase, not assumed — see §2 and §5.

## 2. Problem statement

`EntityReconciliationService.reconcile_fixture`, called from the standard
`SyncOrchestrator.sync_fixtures` path with `sport_code="football"`, appeared to make no progress
over multiple minutes of observation, with the process's CPU usage near zero throughout.

## 3. Reproduction procedure

1. DB safety snapshot taken before any write (see §23).
2. Isolated `reconcile_fixture` call, real production wiring (`build_entity_reconciliation_service`),
   only `SportsProviderRouter`/`SyncOrchestrator`'s own lock/cache substituted with the in-memory
   fallback they already default to (Phase 1's already-validated, orthogonal finding — no local
   Redis instance for that dependency either; unrelated to this phase's root cause).
3. Timed a single raw `redis.asyncio.Redis.set()` call against the real online-feature-store
   client in isolation.
4. Timed `reconcile_fixture` for 15 consecutive real fixtures, one at a time.
5. After the fix, re-ran the real, unmodified `SyncOrchestrator.sync_fixtures` end to end.

## 4. Affected fixture

Premier League (api_football `competition_ref="39"`), season 2022, the full 380-record fetch
result — record 0 (arbitrary, first in fetch order) used for the initial timed reproduction; all
380 processed correctly in §21/§22.

## 5. Exact hang location

Not `reconcile_fixture` itself, and not a hang at all — a genuine, finite, but severely slow
operation. `EntityReconciliationService._compute_form_differential` /
`_compute_transfer_activity` (both called from `reconcile_fixture` whenever `sport_code` is
passed, which the real `SyncOrchestrator.sync_fixtures` path always does) call several
`FixtureFormDifferentialCalculator`/`TransferActivityCalculator.compute_and_write` calculators,
each of which calls `FeatureStoreService.write()` once per feature. `write()`
(`modules/features/application/feature_store_service.py:79-84`, pre-fix) always attempted
`await self.online.set(...)` — a real `redis.asyncio.Redis` call — on every single invocation,
with no memory of a prior failure.

## 6. Timing findings (the actual evidence)

- Raw `client.set()` against the real online-store Redis client (unreachable in this dev
  environment — confirmed no `redis-server`/Docker/Windows service running): fails after
  **exactly 2.00-2.01s**, 6/6 consecutive attempts, identical `TimeoutError: Timeout connecting
  to server` every time — this is `build_redis_client()`'s own `socket_connect_timeout=2`
  firing, not a hang.
- `reconcile_fixture` for one real fixture (record 0, full production wiring, pre-fix): completed
  successfully in **12.211s** — not a timeout, a genuinely slow but terminating call. 12.2s /
  2.0s ≈ 6 online-store write attempts, consistent with the number of football
  form-differential/transfer-activity feature keys this one fixture writes.
- A prior Phase 1 observation window (a few minutes) against a 380-fixture season at ~12s/fixture
  (~76 minutes total) never showed visible progress within that window — explaining why it read as
  an infinite hang rather than a severe slowdown.

## 7. Database findings

No database-level issue found. SQLite transactions committed and released normally throughout
every reproduction; no locked-database errors were observed once the earlier (Phase-1-era, already
resolved) live-dev-server lock contention was out of the picture. Not the root cause.

## 8. Transaction findings

Every `reconcile_fixture` call ran inside one `AsyncSession`, one implicit transaction, closed
normally (`session.commit()`/`session.rollback()` in every reproduction script) with no nested
transactions or leaked connections observed. Not the root cause.

## 9. ORM findings

No lazy-loading loops, no N+1 queries, no relationship recursion found in
`EntityReconciliationService` or the calculators it invokes (read `reconcile_fixture` and its
full call graph — `_resolve`, `_record_ref`, `_emit`, `_compute_form_differential`,
`_compute_transfer_activity`, `_compute_news_market_impact`, `_resolve_prediction_outcomes`,
`_notify_fixture_status_change` — none call back into `reconcile_fixture` or any other
`reconcile_*` method). Not the root cause.

## 10. Provider-ref findings

`provider_ref_index` clean throughout: 0 duplicate `(provider, external_id, entity_kind)` tuples
before or after any reproduction or the real sync verification run (§22). Not the root cause.

## 11. Redis findings — the root cause

`FeatureStoreService.write()`'s online-cache path had a caught exception
(`redis.exceptions.RedisError`, added in an earlier audit fix) but no circuit breaker — every call
independently re-attempted a fresh connection and re-paid the full `socket_connect_timeout` (2s)
regardless of how many prior calls in the same run had already failed. redis-py's async client
does not remember "this Redis was just unreachable" across independent `.set()` calls under this
configuration.

## 12. Cache findings

The *offline* durable write (`self.offline.record(record)`) was never affected — it always
succeeded and was never rolled back by an online-cache failure (that part of the 2026-08-02 audit
fix was already correct). The *online* cache write is what lacked failure-memory. Not a
correctness defect — a pure latency defect.

## 13. Retry findings

No infinite retry loop exists — each `write()` call attempts the online store exactly once and
catches the resulting `RedisError`. The absence of a retry loop is not the issue; the issue is the
absence of any *cross-call* memory that would let a later call skip the attempt.

## 14. Async findings

`asyncio.wait_for` worked correctly throughout — once a `reconcile_fixture` call was genuinely
short (post-fix), `wait_for` returned promptly; the earlier appearance of "cancellation not
working" in Phase 1 was an artifact of the season-level call genuinely needing ~76 minutes
(exceeding every Phase 1 observation window), not a defect in cancellation semantics. No async/
deadlock issue found.

## 15-16. Root cause + evidence

**ROOT CAUSE:** `FeatureStoreService.write()`'s online-cache write path had no circuit breaker —
every call to `online.set()` independently paid the full Redis `socket_connect_timeout` (2s) when
Redis was unreachable, with no memory of prior failures within the same process/run.
`EntityReconciliationService.reconcile_fixture` (football, `sport_code` passed) triggers several
such writes per fixture via its form-differential/transfer-activity/news-market-impact calculator
chain.

**EVIDENCE:** §6's timing data — 2.00-2.01s per raw failed Redis SET (6/6 consecutive, no
change in latency, no backoff), 12.211s for one real fixture reconciliation (≈6 online-store
writes), extrapolating to ~76 minutes for a 380-fixture season — far longer than any prior
observation window, explaining the "infinite hang" misdiagnosis.

**ROOT CAUSE CATEGORY:** REDIS (primary), CACHE (the online feature-store layer specifically).

## 16b. Second, independent bug surfaced by full-suite verification

Running the full `tests/unit` suite (§27, required before this report could be finalized) surfaced
a second, genuinely distinct defect — not a symptom of the same root cause, but a latent bug in
`CircuitBreaker` that the Phase 2 fix newly exposed by giving the breaker a second caller with
different datetime conventions than its original one.

**Failure:** `tests/unit/scripts/test_backfill_both_teams_to_score_training_data.py::test_13_...`
and `::test_14_...` failed with `TypeError: can't subtract offset-naive and offset-aware
datetimes` inside `CircuitBreaker.allow_request`.

**Root cause:** `CircuitBreaker.allow_request`/`record_failure` (`modules/admin/application/
circuit_breaker.py`) never normalized the `now`/`opened_at` datetimes it subtracts. This was never
exposed for its original (and, until this phase, only) caller, `SportsProviderRouter`, which
always passes consistently timezone-aware datetimes. `FeatureStoreService.write()`'s `as_of`
parameter is not always aware — some call sites derive it from a fixture timestamp that has made a
round trip through SQLite, which drops tzinfo on read-back. This is a known, already-documented
condition in this codebase (`docs/decisions.md` ADR-007) with an established, repeated fix idiom
(`_ensure_aware(dt, reference)`) already present standalone in ~20 other application-layer files —
`CircuitBreaker` simply never needed it before because it only ever saw one, internally-consistent
caller.

**Fix:** added the same `_ensure_aware(dt, reference)` helper (module-local, matching this
codebase's existing per-file convention rather than introducing a shared import) to
`circuit_breaker.py`, and applied it symmetrically to both `now` and `state.opened_at` before
subtracting in `allow_request`. No behavior change for `SportsProviderRouter` (its datetimes are
always already aware, so both `_ensure_aware` calls are no-ops for it) — the fix is additive
robustness, not a semantic change to circuit-breaking logic, threshold, or recovery timeout for
any existing caller.

**Verification:** re-ran the 2 previously-failing tests plus
`tests/unit/modules/features/test_feature_store_service.py` plus `tests/unit/modules/admin` (the
circuit breaker's own test suite) — **156 passed, 0 failed**. Then re-ran the complete `tests/unit`
suite end to end (§27) to confirm no other test depends on the old (buggy) behavior.

## 17. Fix implemented

`modules/features/application/feature_store_service.py`: `FeatureStoreService` gained an optional
`circuit_breaker: CircuitBreaker | None = None` field (default `None` — every existing
caller/test unaffected). `write()` now checks `circuit_breaker.allow_request(...)` before
attempting `online.set()`, records success/failure, and skips the attempt entirely once the
breaker is `OPEN` — degrading exactly like a caught `RedisError` (offline record already durable),
just without the latency. `CircuitBreaker` is the **same class** `SportsProviderRouter` already
uses for provider calls (`modules/admin/application/circuit_breaker.py`) — no second breaker
implementation, keyed separately (`"feature_store:online"`) so it never collides with a provider
key. `apps/api/composition.py`'s `build_feature_store_service` now passes the existing process-
wide `get_circuit_breaker()` singleton. No other file changed; `EntityReconciliationService`,
`SportsProviderRouter`, `SyncOrchestrator`, `provider_ref_index`, provenance, quota controls, and
every other architecture component are untouched.

Verified post-fix (real, unmodified production wiring): the first fixture in a season still pays
the initial failure cost (~10s while the breaker opens across its own several feature writes,
matching the measured pre-fix 12.211s minus the writes that now short-circuit even within record
0); every subsequent fixture in the same run completed in **0.1-0.4s** (down from ~12s) — a
roughly 30-100x speedup, turning a ~76-minute season into roughly 30-90 seconds.

## 18. Regression test

`tests/unit/modules/features/test_feature_store_service.py`, new `TestOnlineStoreCircuitBreaker`
class, 3 tests:
- `test_breaker_stops_calling_online_store_after_failure_threshold` — proves the online store
  stops being called at all once the breaker opens (call-counting fake).
- `test_offline_write_still_succeeds_and_is_correct_regardless_of_breaker_state` — proves the
  breaker never affects correctness, only latency; every write's durable record and returned value
  are correct across 5 writes regardless of breaker state.
- `test_breaker_recovers_once_recovery_timeout_elapses` — proves self-healing (HALF_OPEN trial
  request) once the recovery window passes, the same behavior the existing provider breaker
  already has.

All 23 tests in the file pass (20 pre-existing + 3 new).

## 19. Real fixture test

Documented in §6 (pre-fix: 12.211s for one real fixture) and §17 (post-fix: sub-second per fixture
after the breaker opens) — both against the real Premier League 2022 fetch, real production
wiring, no mocks for anything except the orchestrator-level lock/cache (Phase 1's already-
validated, unrelated substitution).

## 20. Normal SyncOrchestrator test

Ran the real, unmodified `SyncOrchestrator.sync_fixtures("football", "81", "2024", season_id, now,
trigger=SyncTrigger.BACKFILL, force=True)` — DFB-Pokal 2024, 63 fixtures, smallest already-
accessible season, chosen to minimize API quota use. Result: **completed in 17.3s**,
`fetched=63 created=0 updated=63 rejected=0 status=succeeded`. This is the real production path —
`SportsProviderRouter` → `ApiFootballAdapter` → `SyncOrchestrator` →
`EntityReconciliationService` → `provider_ref_index` → canonical entities — proven healthy
end to end, no Phase 1 workaround involved.

## 21. Provider API calls

1 attempted (api-football `/fixtures?league=81&season=2024`), 1 succeeded, 0 failed.

## 22. API quota impact

Minimal — a single real request against an already-accessible, already-synced season (a resync,
not new data), chosen deliberately over touching an unaccessed season to avoid any quota risk.

## 23. Database before/after

| | Before (Phase 2 start) | After |
|---|---|---|
| `dev.db` size | 170,553,344 bytes | 170,553,344 bytes (unchanged — resync only updated existing rows) |
| `dev.db` sha256 | `dfef6bdd60d5949e7302c6dc4347ebc1c5236d166a496c16b011df7eb6328323` | not re-hashed (binary content legitimately changed — `updated_at`/`version` bumps on 63 rows) |
| fixtures | 7,829 | 7,829 |
| teams | 243 | 243 |
| competitions | 7 | 7 |
| seasons | 22 | 22 |
| provider_ref_index | 8,570 | 8,570 |
| predictions | 28,443 | 28,443 |
| prediction_outcomes | 28,401 | 28,401 |
| models | 168 | 168 |
| champions | 40 | 40 |
| datasets | 155 | 155 |
| calibration_reports | 0 | 0 |

Zero rows created or deleted anywhere — the real sync correctly recognized all 63 DFB-Pokal 2024
fixtures as already-reconciled and updated them in place (`created=0, updated=63`), re-confirming
their `period_scores` (63/63 still populated, integrity intact).

## 24. Provider_ref_index before/after

0 duplicate `(provider, external_id, entity_kind)` entries before and after. 0 duplicate fixture
rows (`season_id, home_team_id, away_team_id, scheduled_at`) before and after.

## 25. Provenance verification

All 4 Phase 1 Champions confirmed byte-identical after this phase's sync run — same `model_key`,
`algorithm`, `status='champion'`, `calibration_ref=NULL`, and `trained_at` timestamp
(`2026-08-18 20:41:05.270440`) as recorded at the end of Phase 1. Not retrained, not
recalibrated, not replaced.

## 26. Cross-sport verification

`pytest tests/unit/modules/features tests/unit/modules/ingestion tests/unit/modules/sports -q` →
**639 passed, 0 failed** — covers team/competition/season/fixture reconciliation,
`provider_ref_index`, and provider routing for football, basketball, and baseball alike. The fix
is scoped to `FeatureStoreService`, a shared component every sport's calculators already went
through identically before and after this change (only football has any calculators registered
today — see `entity_reconciliation_service.py`'s own docstrings — so basketball/baseball fixture
reconciliation was never exposed to this particular latency in the first place, but the shared
`FeatureStoreService`/`CircuitBreaker` code itself is exercised and passes).

## 27. Full test results

- `tests/unit/modules/features/test_feature_store_service.py`: 23 passed (20 existing + 3 new).
- `tests/unit/modules/features + ingestion + sports`: 639 passed.
- `tests/unit/modules/predictions`: 943 passed.
- `tests/unit` (full backend suite), **first run** (before the §16b fix): **2621 passed, 2
  failed, 0 skipped**, 1858.94s. Both failures traced to the same root cause (§16b) and were not
  present in the targeted module runs above because neither `tests/unit/scripts/` nor a full-suite
  run had been exercised yet at that point.
- `tests/unit/scripts/test_backfill_both_teams_to_score_training_data.py` +
  `tests/unit/modules/features/test_feature_store_service.py` + `tests/unit/modules/admin`
  (targeted re-run after the §16b fix): **156 passed, 0 failed**.
- `tests/unit` (full backend suite), **final run** (after the §16b fix): **2623 passed, 0
  failed, 0 skipped**, 1589.36s (0:26:29). Same total test count as the first run (2621 + 2 =
  2623), confirming the fix resolved both failures without changing collection/count anywhere
  else in the suite.

**BASELINE TESTS:** 2621 passed / 2 failed / 0 skipped (first full-suite run, pre-§16b-fix)
**FINAL TESTS:** 2623 passed / 0 failed / 0 skipped (final full-suite run, post-§16b-fix)

## 28. Regressions

One regression was introduced by this phase's own fix and caught by its own required full-suite
run before delivery (§16b) — not shipped. `CircuitBreaker.allow_request` crashed on
naive/aware-datetime comparison once `FeatureStoreService` became its second caller. Fixed with
the codebase's own established `_ensure_aware` idiom (ADR-007), re-verified in isolation (156/156)
and via a second complete full-suite run (2623/2623 passed). No other regressions detected in
either full-suite run.

## 29. Remaining risks

- `FeatureStoreService.read()` has the same theoretical per-call Redis-timeout exposure as
  `write()` had — it is not currently invoked from `EntityReconciliationService.reconcile_fixture`
  or any of its calculators (confirmed by reading every calculator in this phase's audit — all of
  them only ever call `store.write()`), so it was deliberately left untouched to keep this fix
  minimal and scoped to the actual reported defect. Worth the same breaker treatment as a small
  follow-up if a future caller starts reading through this path during a Redis outage.
- The free-tier api-football plan restriction (seasons outside 2022-2024) remains, unchanged from
  Phase 1 — out of scope for this phase.
- No local Redis instance exists in this dev environment at all — the circuit breaker makes an
  unreachable Redis fast and harmless rather than slow, but does not make the online cache
  actually available. Standing up a real dev Redis instance (or documenting that its absence is
  an accepted, permanent dev-environment state) remains an open operational question outside this
  phase's scope.

## 30. Recommended Phase 3

Apply the same circuit-breaker treatment to `FeatureStoreService.read()` for symmetry (§29), then
resume the originally-planned historical-data-expansion work (2021/2025/2026 seasons, or a
supplementary provider for the 552 historical-web fixtures with no half-time source) now that the
standing `SyncOrchestrator.sync_fixtures` path is confirmed healthy and fast enough for real
production use — no narrower workaround script should be needed going forward.
