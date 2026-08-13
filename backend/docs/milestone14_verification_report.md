# Milestone 14 Verification Report — Historical News → Historical Feature Reconstruction Integration

## 1. Executive Summary

Connects the Milestone 13 historical news intelligence layer to real, market-specific historical
feature reconstruction, at the smallest safe integration point the audit could find: extending the
existing, unchanged, well-tested `NewsMarketImpactEngine` (Milestone 9/10) with one additive
parameter, plus a new, thin orchestration/auditability service on top of it. No new market
registry, feature registry, provenance system, or entity-resolution system was created. Historical
relevance never bypasses `NewsEvent.is_feature_eligible()` — the existing Milestone 9 provenance
gate remains fully authoritative, verified directly by test.

## 2. Initial Audit Findings

The audit (`NewsMarketImpactEngine.team_contributions`, formerly private `_team_contributions`)
found the exact gap this milestone needed to close: the engine already implements almost
everything Phase 8 asks for — event eligibility (`is_feature_eligible()`), kickoff-gating
(`is_information_available_before_kickoff`), market-specific rules (`MARKET_IMPACT_RULES`) — but
its roster lookup (`players.list_by_team`) was always *current* team membership, never historically
accurate. This is precisely the class of bug Milestone 13's own audit named: if this engine were
ever invoked for a historical (already-completed) fixture, a player who has since transferred away
would be wrongly excluded from that historical roster, and one who has since transferred in would
be wrongly included.

A second audit finding: `DatasetBuilder` (Milestone 9.1) sources training samples exclusively from
`Prediction.feature_snapshot`, never re-deriving features retroactively — "no algorithm may bypass
the Feature Store" is enforced by construction. This milestone does not touch that boundary; it
makes historically-correct feature *values* available in the offline Feature Store (the same store
`PredictionContextBuilder` already reads from), which is the correct layer to extend — building a
second, parallel write path into `Prediction.feature_snapshot` directly would have duplicated
existing architecture, which this milestone was explicitly told not to do.

## 3. Files Created

- `modules/predictions/application/historical_feature_reconstruction_service.py` —
  `HistoricalFeatureReconstructionService`, `NewsFeatureEligibility`,
  `HistoricalFeatureReconstructionResult`.
- `tests/unit/modules/predictions/test_news_market_impact_engine_historical.py` (8 tests).
- `tests/unit/modules/predictions/test_historical_feature_reconstruction_service.py` (11 tests).
- `docs/milestone14_verification_report.md` (this report).

## 4. Files Modified

- `modules/predictions/application/news_market_impact_engine.py` — added an optional
  `historical_reference_time: datetime | None = None` parameter to `team_contributions`/
  `compute_and_write`, and two new optional constructor fields (`transfers`,
  `historical_entity_resolution`), both defaulting to `None` so every pre-existing caller's
  construction and behavior is unchanged (verified: all 10 pre-existing tests pass unmodified).
  `_team_contributions`/`_feature_key` were renamed to public (`team_contributions`/`feature_key`)
  since `HistoricalFeatureReconstructionService` now legitimately calls them from outside the
  class — no other behavior change.
- `apps/api/composition.py` — `build_football_news_market_impact_engine` now also wires
  `transfers`/`historical_entity_resolution` (harmless when unused); added
  `build_historical_feature_reconstruction_service`.

## 5. Historical Fixture Matching

Not implemented as a separate class — the audit found Milestone 13's own
`HistoricalNewsRelevanceEngine` already fully answers "was this article relevant to this specific
historical fixture," given the fixture's own immutable `home_team_id`/`away_team_id`/`scheduled_at`
as an explicit, caller-supplied `HistoricalFixtureContext`. Building a second matcher would have
duplicated it. `HistoricalFeatureReconstructionService.audit_events_for_fixture` calls it directly.

## 6. Historical Entity Resolution Integration

`NewsMarketImpactEngine._resolve_roster` (new, private) is the actual integration point: when
`historical_reference_time` is given, roster candidates come from `transfers.list_by_team` (a real,
bounded query) and each candidate's membership is independently re-verified via
`HistoricalEntityResolutionService.resolve_player_membership` at that exact time — never `Player.
team_id`, never a Knowledge Graph `PLAYS_FOR` edge. This fails closed: a caller passing
`historical_reference_time` without also wiring `transfers`/`historical_entity_resolution` gets a
clear `ValueError`, never a silent fallback to current-roster reads. Verified structurally (a test
inspects `_resolve_roster`'s own source and asserts it never references `kg_nodes`) and
behaviorally (a player's own `team_id` field is deliberately set to a *different* team than the
Transfer chain says, and every test confirms the Transfer chain wins).

## 7. Historical News Relevance Integration

`HistoricalFeatureReconstructionService.audit_events_for_fixture` calls
`HistoricalNewsRelevanceEngine.resolve_relevance` directly (Milestone 13, unmodified) for
per-event auditability — the one thing `NewsMarketImpactEngine`'s aggregate roster scan cannot
provide on its own (it returns only summed dimension totals, never which candidate events
contributed or why an ineligible one was excluded). This satisfies Phase 8 item 7 ("preserve
unresolved/ineligible events for auditability") without duplicating the relevance engine itself.

## 8. Market-Specific Relevance

`MARKET_IMPACT_RULES`/`MarketImpactRegistry` (Milestone 9) were not modified. The audit method
optionally checks market eligibility via the same `market_rule_exists` callable
`HistoricalNewsRelevanceEngine` already uses (composed once, in `apps/api/composition.py`,
reused here) — an event relevant to the fixture but with no rule for the requested market
correctly reports `NEWS_MARKET_UNRESOLVED`, never assumed relevant to every market equally
(verified: the same event is `NEWS_FEATURE_ELIGIBLE` for `football.total_goals_over_under`, a
market with a real forward-injury rule, and `NEWS_MARKET_UNRESOLVED` for `football.corners`,
which has none).

## 9. Provenance Enforcement

`NewsEvent.is_feature_eligible()` (Milestone 9, unchanged) remains the sole authority for whether
an event can ever contribute a published feature. `_classify` (the audit method's own
classification logic) explicitly checks it only *after* confirming `HISTORICALLY_RELEVANT` — and
even then, additionally re-applies Milestone 10's kickoff check
(`is_information_available_before_kickoff`) so the audit's verdict can never diverge from what
`compute_and_write`'s own kickoff parameter would actually publish. Verified directly: an event
classified `HISTORICALLY_RELEVANT` by the Milestone 13 engine, but whose
`availability_classification` is `UNKNOWN_AVAILABILITY_TIME` (the real state of every
`BACKFILL`/`ADMIN_MANUAL` event today), is reported `NEWS_FEATURE_INELIGIBLE` — and the event's own
`availability_classification` field is confirmed unchanged by the call (this service never mutates
an event's provenance).

## 10. Feature Eligibility Behavior

The full table below is enforced and tested:

| Relevance (M13) | `is_feature_eligible()` | Before kickoff | `NewsFeatureEligibility` |
|---|---|---|---|
| `HISTORICALLY_RELEVANT` | True | True | `NEWS_FEATURE_ELIGIBLE` |
| `HISTORICALLY_RELEVANT` | False (e.g. `UNKNOWN_AVAILABILITY_TIME`) | — | `NEWS_FEATURE_INELIGIBLE` |
| `HISTORICALLY_RELEVANT` | True | False (post-kickoff) | `NEWS_FEATURE_INELIGIBLE` |
| `ENTITY_UNRESOLVED` | — | — | `NEWS_ENTITY_UNRESOLVED` |
| `HISTORICALLY_UNRESOLVED` | — | — | `NEWS_FIXTURE_UNRESOLVED` |
| `MARKET_UNRESOLVED` | — | — | `NEWS_MARKET_UNRESOLVED` |
| `NOT_RELEVANT` / `INSUFFICIENT_PROVENANCE` | — | — | `NEWS_FEATURE_INELIGIBLE` |

`HISTORICALLY_RELEVANT` alone never implies eligibility — verified directly, matching the
milestone's own stated non-negotiable.

## 11. Feature Reconstruction Behavior

`HistoricalFeatureReconstructionService.publish_for_fixture` is the only write path — a thin,
explicit passthrough to the existing `NewsMarketImpactEngine.compute_and_write` for both fixture
sides, passing `historical_reference_time` for all three of `now`/`kickoff`/
`historical_reference_time` (documented in the code: `now` must be the historical moment, not
today's wall clock, or TTL/age checks would treat every historical event as expired). Writes
nothing for a dimension with no feature-eligible evidence — the same "unavailable, never a
fabricated zero" semantics `NewsMarketImpactEngine` already had. If no candidate events exist or
none are eligible, the method returns `[]` without raising — the existing non-news feature
pipeline is untouched either way, since this service has no dependency capable of blocking it.

## 12. Feature Provenance

`HistoricalFeatureReconstructionResult` carries `article_id`, `news_event_id`, `fixture_id`,
`availability_classification`, `eligibility`, and the full embedded Milestone 13
`HistoricalRelevanceResult` (itself carrying `reference_time`, `information_available_at`,
`entity_resolution`, `membership_resolution`, `fixture_resolution`, `market_resolution`, and a
named evidence trail) — nothing fabricated, nothing collapsed into a bare boolean.

## 13. Feature Versioning

No new versioning mechanism was introduced. Published features go through the existing,
unmodified `FeatureRegistrationService`/`FeatureStoreService` write path (`NewsMarketImpactEngine.
ensure_registered` + `store.write`), which already carries the feature's own registered version
via `FeatureDefinition` — reused exactly as every other feature already does.

## 14. Leakage Protections

Full A–P matrix from the spec, each with a direct test:

- **E** (later transfer doesn't affect an earlier reconstruction), **F** (current `Player.team_id`
  conflict — Transfer chain wins), **G** (structural: `_resolve_roster`'s historical branch never
  references `kg_nodes`), **H** (insufficient Transfer coverage → excluded, not guessed) — in
  `test_news_market_impact_engine_historical.py`.
- **B/M** (post-kickoff information never pre-match eligible), **C/D/K** (`UNKNOWN_AVAILABILITY_TIME`
  never eligible, event's own classification unchanged), **I/J/P** (market-specific gating, one
  market's rule never satisfies another's), **L** (an event about an unrelated team/fixture doesn't
  leak in), **N** (structural: the service has no fixture-repository dependency, so it cannot
  substitute a "current" fixture for the one explicitly supplied), **O** (no candidate events →
  no-op, never raises) — in `test_historical_feature_reconstruction_service.py`.
- **A** is the positive control (a genuinely eligible, pre-kickoff, verified event *is* published)
  — covered by both new files.

## 15. Test Matrix

19 new tests, all passing, none touching a real external API:

- `test_news_market_impact_engine_historical.py` — 8 tests (fail-closed without required
  dependencies; basic historical roster reconstruction; roster excludes a never-historically-member
  player; leakage E/F/G/H; live/current mode byte-identical when the new parameters are omitted).
- `test_historical_feature_reconstruction_service.py` — 11 tests (the full eligibility
  classification matrix; leakage B/L/N/O/P; the actual `publish_for_fixture` write path, confirming
  both sides are written and correctly stamped at the historical timestamp).

## 16. Regression Results

- Targeted (`modules/predictions`, `modules/intelligence`, `apps/`): **1361 passed, 0 failed.**
- Full suite: **2180 passed, 58 skipped, 0 failed.** Milestone 13 baseline was 2161 passed, 58
  skipped, 0 failed — delta is exactly **+19** (the new test count above), skip count unchanged,
  zero failures, no existing test modified to hide a regression. The 10 pre-existing
  `NewsMarketImpactEngine` tests pass completely unmodified.

## 17. Database/Migration Status

None required or created. Read-only inspection of `dev.db` confirms zero writes this milestone:

```
transfers: 308 rows (unchanged)
news_events: 68 rows, all still UNKNOWN_AVAILABILITY_TIME (unchanged)
feature_values_offline WHERE feature_key LIKE 'news.%': 0 rows (unchanged — nothing has ever
  been published, live or historical; neither new service was invoked against dev.db)
```

## 18. External API Status

Zero live RSS calls, zero Gemini calls, zero real news backfills. `NEWS_BACKFILL_ENABLED` and
`NEWS_SYNC_ENABLED` were not touched by this milestone and remain `False` by their existing
defaults. Every test uses in-memory fakes; nothing in this milestone's code path ever constructs a
real provider adapter.

## 19. Training/Model Status

No `model.fit()` call, no training, no retraining, no recalibration, no Champion/Production model
change, no change to `PredictionEngine` or any prediction endpoint. `DatasetBuilder`'s exclusive
`Prediction.feature_snapshot` sourcing was not touched — this milestone makes correctly-gated
historical feature *values* available in the offline Feature Store; nothing in this milestone
reads them back into a training dataset (explicitly out of scope, see §21).

## 20. Production Impact

None. `apps/worker/bootstrap.py`, Celery Beat schedules, provider configuration, and every existing
prediction endpoint are untouched. Neither new service is wired into any live endpoint, Celery
task, or script by this milestone — both are currently reachable only via
`apps/api/composition.py`'s new builders, exactly the same "built, composed, not yet wired into a
live caller" posture Milestone 13's own two services had before this milestone connected one of
their consumers.

## 21. Known Limitations

- Neither `HistoricalFeatureReconstructionService` nor the extended `NewsMarketImpactEngine`
  historical path is invoked by any live endpoint, Celery task, or backfill script yet — this
  milestone built and proved the safe capability; wiring it into an actual historical-training-data
  script (in the style of the existing `scripts/backfill_*_training_data.py` one-offs) remains
  future work.
- `_resolve_roster`'s historical branch finds candidates via `transfers.list_by_team` — a player
  who has *never* transferred while tracked (no Transfer record exists for them at all, on either
  side) cannot be found this way, the same Transfer-coverage floor Milestone 13 already documented.
- `audit_events_for_fixture` always uses `event.information_available_at` as the reference time
  (Milestone 13's documented default) — since this is `None` for every real `BACKFILL`/
  `ADMIN_MANUAL` event today, no real historical article can currently reach
  `NEWS_FEATURE_ELIGIBLE` through this path. This is intentional, not a defect: it is exactly the
  "if this chain cannot be proven, exclude from training" principle this whole milestone sequence
  exists to enforce.

## 22. Deferred Work

- Wiring `HistoricalFeatureReconstructionService.publish_for_fixture` into an actual historical
  training-data backfill script, so a future retraining pass could draw on genuinely
  historically-safe news features for markets/fixtures that currently have none.
- A dataset-eligibility classifier combining this milestone's `NewsFeatureEligibility` with
  Milestone 9's `NewsAvailabilityClassification` into one final training-row-level verdict (the
  spec's own "Dataset Audit" framing) — not built, since no training dataset currently consumes
  these values at all.
- Any real backfill execution, `NEWS_BACKFILL_ENABLED` activation, or live scheduled news sync —
  remain separate, explicit approvals per Milestone 12's own closing instruction, unchanged here.

## 23. Recommended Milestone 15 Scope

The most natural next step, if pursued: extend one of the existing `scripts/backfill_*_training_
data.py` one-off scripts (which already construct historical `Prediction.feature_snapshot` rows by
querying the Feature Store per-fixture) to additionally call `HistoricalFeatureReconstructionService.
publish_for_fixture` before reading the snapshot's news-derived features — the exact "smallest
safe integration point" this milestone's own services were built to support, requiring no further
new infrastructure. This should remain a separate, explicitly-approved milestone, not started here.

---

**MILESTONE 14 COMPLETE.** Per the governing rule, this stops here — Milestone 15 is not started
automatically, no model was trained, no real news backfill was performed, `NEWS_BACKFILL_ENABLED`
and `NEWS_SYNC_ENABLED` remain false, and no live external API was contacted. Waiting for explicit
approval before proceeding.
