# Milestone 13 Verification Report — Historical News Point-in-Time Reconstruction & Training Safety

## 1. Objective

Build the application-layer infrastructure required to determine whether historical news was
relevant to a historical fixture/event using only information that would genuinely have been
knowable at the time — never current team membership, never current Knowledge Graph state, never
future information. This is a provenance and training-safety layer, not a feature that changes any
live prediction behavior.

## 2. Audit Findings (Phase 1, approved before implementation)

The audit (performed read-only, directly against `dev.db`) found one critical structural fact that
drove the entire design: two candidate sources exist for "who was on which team at time T," and
only one is trustworthy.

| Source | Reliable for point-in-time? | Evidence |
|---|---|---|
| `Player.team_id` | No | Single mutable field, no history retained, overwritten on every re-sync |
| KG `PLAYS_FOR` edges | No, in practice | Schema is temporal (`KGEdge.valid_from`/`valid_to`, Milestone 7) but nothing in the real pipeline ever closes an edge — confirmed live: **100 `plays_for` edges exist, 0 have ever been superseded**. The only code that calls `TemporalGraphService.supersede_edge` for a transfer (`KnowledgeGraphEnrichmentService`) has zero real call sites anywhere in `apps/`. |
| `Transfer.effective_date` | **Yes** | Real, provider-backed, append-only — 308 records, spanning 2010-09-17 to 2026-07-22 |

**Determination: no migration required.** Every field needed already exists
(`Transfer.effective_date`, `Fixture.scheduled_at`/`home_team_id`/`away_team_id`,
`NewsEvent.information_available_at`). The gap was entirely at the application layer — nothing
performed point-in-time membership resolution via `Transfer` chaining, and no Mode 2 (historical)
relevance engine existed. Approved and implemented on this basis.

## 3. Temporal Model

For a historical fixture `F`: `F.scheduled_at` is the kickoff, and `F.home_team_id`/`away_team_id`
are immutable facts by construction — a `Fixture` row already *is* the point-in-time snapshot of
who played, never re-derived from a team's current schedule.

For a news event `N`, the historical reference time is an **explicit, caller-supplied parameter**
(`resolve_relevance(event, reference_time, fixture_context)`), never read internally off any
field. This matches the spec's own interface shape and keeps the engine honest: it never decides
for itself what counts as a trustworthy reference time. The documented, correct default caller
behavior is to pass `NewsEvent.information_available_at` (Milestone 9's existing field) — which,
by the unchanged Milestone 9 rule, is `None` for every `BACKFILL`/`ADMIN_MANUAL` event today.
Passing `None` always yields `INSUFFICIENT_PROVENANCE`. This is intentional, not a defect: it
means historically-backfilled articles are correctly excluded from ever reaching
`HISTORICALLY_RELEVANT` today, exactly matching the milestone's own governing principle ("if this
chain cannot be proven, exclude from training").

## 4. Historical Entity Resolution

`HistoricalEntityResolutionService.resolve_player_membership(player_id, reference_time)`
(`modules/intelligence/application/historical_entity_resolution_service.py`, new) depends on
**only** `TransferRepositoryPort` — structurally incapable of consulting `Player.team_id` or any
Knowledge Graph edge, since it has no dependency through which to reach either (verified directly
by a test inspecting the dataclass's own field set).

Algorithm: fetch `transfers.list_by_player(player_id)`, sort by `effective_date`, take the latest
transfer whose `effective_date <= reference_time`.

- If none exists (no transfers at all, or `reference_time` predates the earliest known transfer):
  `HISTORICALLY_UNRESOLVED`, `team_id=None` — never filled in from any other source.
- If one exists: `HISTORICALLY_RESOLVED`, `team_id` = that transfer's `to_team_id` — which may
  itself be `None` (a genuinely evidenced "released, no club" state, distinct from missing
  evidence).

## 5. Historical Relevance Engine

`HistoricalNewsRelevanceEngine` (`modules/intelligence/application/historical_news_relevance_engine.py`,
new) is a Mode 2 sibling to Mode 1's `NewsRelevanceFilter`/`build_fixture_relevance_vocabulary`
(Milestone 10/12) — neither was modified. Its only dependencies are `kg_nodes`, `entity_resolution`,
and an optional `market_rule_exists` callable — no `FixtureRepositoryPort`/`TeamRepositoryPort`/
`PlayerRepositoryPort` (Mode 1's "currently upcoming" dependencies), so it is architecturally
incapable of building or consulting a current-fixture vocabulary (verified by a dedicated
structural test).

For each `RESOLVED` entity mention on the event: a `TEAM` mention is compared directly against
`fixture_context.home_team_id`/`away_team_id`; a `PLAYER` mention is resolved via
`HistoricalEntityResolutionService` at the given `reference_time`, then the resolved team (if any)
is compared the same way. The engine never looks up "this team's current fixture" or "this
player's current team" at any point.

## 6. Historical Classification Taxonomy (additive)

`HistoricalRelevanceClassification`: `HISTORICALLY_RELEVANT`, `NOT_RELEVANT`,
`HISTORICALLY_UNRESOLVED`, `ENTITY_UNRESOLVED`, `MARKET_UNRESOLVED`, `INSUFFICIENT_PROVENANCE`
(`NOT_RELEVANT` added beyond the spec's named minimum set, needed for the "resolved but doesn't
match" case). This is a wholly separate dimension from the existing Milestone 9
`NewsAvailabilityClassification` (`VERIFIED_PRE_MATCH`/`UNKNOWN_AVAILABILITY_TIME`/`INVALID`) —
neither taxonomy was merged into or replaced the other.

## 7. Provenance Safety

The engine never writes to `NewsEvent.availability_classification` or `information_available_at`
— it only reads them (for reporting in `HistoricalRelevanceResult`) and never mutates the event.
Tests confirm directly: an event pre-set to `UNKNOWN_AVAILABILITY_TIME` (the real state of every
`BACKFILL`/`ADMIN_MANUAL` event today) can be classified `HISTORICALLY_RELEVANT` by this engine
while its own `availability_classification` stays `UNKNOWN_AVAILABILITY_TIME` and
`is_feature_eligible()` stays `False` — proving historical relevance can never bypass the existing,
unchanged Milestone 9 eligibility gate. `classify_news_availability` itself (the single choke
point for `VERIFIED_PRE_MATCH`) was not touched by this milestone.

## 8. Market-Specific Relevance

`MarketImpactRegistry`/`MARKET_IMPACT_RULES` (Milestone 9) were not modified. Market resolution is
injected as a `market_rule_exists: Callable[[NewsEventType, str], bool]` port on the engine, with
the real implementation composed in `apps/api/composition.py` (`_market_rule_exists`, querying
`MARKET_IMPACT_RULES` read-only) — this keeps `modules.intelligence` free of a new dependency on
`modules.predictions`, preserving the same one-directional module-boundary posture already
documented for `modules.ingestion`. Requesting relevance for a market with no registered rule
correctly downgrades an otherwise-relevant result to `MARKET_UNRESOLVED`, never assumed relevant.

## 9. Mode Separation

Verified structurally (dataclass field inspection tests) for both new services, and behaviorally
via the leakage tests (§11) — Mode 2 never reads fixture/team/player data outside what its caller
explicitly supplies as `fixture_context`, so it cannot influence or be influenced by Mode 1's live
upcoming-fixture relevance filtering, which remains completely untouched.

## 10. Database Impact

None. No migration was written or is needed — every field this milestone reads already existed.
Read-only inspection (§13) confirms zero writes of any kind occurred.

## 11. Leakage Tests

Two explicit tests per spec §15: (a) a transfer with `effective_date` *after* the article's
availability time never changes the resolution computed for that article; (b) historical transfer
evidence is used even when it would disagree with a hypothetical "current" team (never consulted,
since the service has no path to reach it). Both pass, alongside the full A–U scenario matrix from
the approval directive (item U — "current aliases are only ever an approximation" — is a
structural property: the engine never reads `KGNode.aliases` anywhere in its own code, so no
runtime test was needed beyond code inspection, noted here for the record).

## 12. Files Created

- `modules/intelligence/application/historical_entity_resolution_service.py`
- `modules/intelligence/application/historical_news_relevance_engine.py`
- `tests/unit/modules/intelligence/test_historical_entity_resolution_service.py` (9 tests)
- `tests/unit/modules/intelligence/test_historical_news_relevance_engine.py` (17 tests)
- `docs/milestone13_verification_report.md` (this report)

## 13. Files Modified

- `apps/api/composition.py` — added `build_historical_entity_resolution_service`,
  `build_historical_news_relevance_engine`, `_market_rule_exists` (the only real composition-root
  glue this milestone required; no existing builder was changed).

## 14. Tests

26 new tests, all passing, none touching a real external API or requiring a schema change:

- `test_historical_entity_resolution_service.py` — items A–H from the spec's own test list
  (transfer history present/absent/multiple/before/after, missing history, reference time before
  earliest transfer, release-with-no-club, structural + behavioral proof that current
  `Player.team_id` is never consulted).
- `test_historical_news_relevance_engine.py` — items J–T, Case 1 (current-fixture bias structurally
  impossible), 2 leakage tests (§15), and a mode-separation structural test.

## 15. Regression Results

- Targeted (`modules/intelligence`, `apps/`): **693 passed, 0 failed.**
- Full suite: **2161 passed, 58 skipped, 0 failed.** Milestone 12 baseline was 2135 passed, 58
  skipped, 0 failed — delta is exactly **+26** (the new test count above), skip count unchanged,
  zero failures, no existing test modified.

## 16. `dev.db` Verification (read-only, no writes)

```
transfers: 308 rows (unchanged)
news_articles: 199 rows (unchanged)
intelligence_sync_runs (trigger='backfill'): 0 rows (unchanged — M12's backfill remains unused)
news_events by availability_classification: {'UNKNOWN_AVAILABILITY_TIME': 68} (unchanged)
kg_edges (plays_for, superseded): 0 rows (unchanged — confirms the audit's own finding still holds)
```

`NEWS_BACKFILL_ENABLED` and `NEWS_SYNC_ENABLED` were not touched by this milestone and remain
`False` by their existing defaults (no config file was modified).

## 17. External API / Model-Training Status

No live RSS call, no live Gemini call, no real backfill execution occurred at any point. No model
was trained, retrained, or promoted; no production Champion changed; no prediction behavior
changed — this milestone added two new, currently-unwired application services and their tests
only. Neither service is called from any existing endpoint, task, or pipeline yet — that wiring
(deciding *when* and *where* historical reconstruction should actually run, e.g. as part of a
future dataset-construction step) is explicitly out of this milestone's scope.

## 18. Known Limitations

- Historical alias validity (`KGNode.aliases`) is not temporally tracked — the audit already
  established this; this milestone did not add temporal aliasing (explicitly deferred per spec
  §8, "leave it as a documented extension point rather than implementing speculative data").
- `Transfer` coverage has a real floor: for any player/time predating that player's earliest known
  transfer record, membership is honestly `HISTORICALLY_UNRESOLVED` — there is no way to improve
  this without either backfilling more transfer history or accepting a documented coverage gap.
- The two new services are not yet wired into any real training-dataset-construction path — this
  milestone built the safety-checked building blocks; assembling them into an actual "historical
  news feature for training" pipeline (with the explicit exclusion-reason bookkeeping the spec's
  §12/"Dataset Audit" sections describe) remains future work.

## 19. Deferred Work

- Wiring `HistoricalNewsRelevanceEngine` into an actual training-dataset construction path, with
  the full exclusion-reason audit trail the spec's Dataset Audit section describes.
- A dataset-eligibility classifier that combines this milestone's `HistoricalRelevanceClassification`
  with Milestone 9's `NewsAvailabilityClassification` into one final training-eligibility verdict.
- Any real backfill execution or `NEWS_BACKFILL_ENABLED` activation — remains a separate, explicit
  approval per Milestone 12's own closing instruction, unchanged by this milestone.

---

**MILESTONE 13 IMPLEMENTATION COMPLETE.** Per the governing rule, this stops here — Milestone 14 is
not started automatically, no real backfill was performed, `NEWS_BACKFILL_ENABLED` and
`NEWS_SYNC_ENABLED` remain false, and no model was trained. Waiting for explicit approval before
proceeding.
