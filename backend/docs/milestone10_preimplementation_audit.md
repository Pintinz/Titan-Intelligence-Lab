# Milestone 10 — Pre-Implementation Audit (Phase 1, read-only)

No files were modified during this investigation.

## Files inspected

- `modules/intelligence/domain/value_objects.py`, `modules/intelligence/domain/entities.py`
- `modules/intelligence/application/news_ingestion_service.py`
- `modules/intelligence/application/intelligence_enrichment_orchestrator.py`
- `modules/intelligence/application/news_provenance.py`, `news_validity_policy.py`
- `modules/intelligence/infrastructure/providers/rss_news_provider.py`
- `modules/intelligence/infrastructure/gemini_adapter.py`
- `modules/intelligence/infrastructure/persistence/models.py`
- `modules/predictions/application/news_market_impact_engine.py`
- `modules/ingestion/domain/value_objects.py` (`SyncTrigger`, for comparison)
- `modules/ingestion/application/sync_orchestrator.py` (`sync_upcoming_structured_intelligence`)
- `modules/ingestion/application/provenance.py` (`_env_int` convention)
- `modules/ingestion/infrastructure/celery/{celery_app.py, beat_schedule.py, tasks.py, dead_letter.py}`
- `modules/predictions/infrastructure/celery/tasks.py` (cross-module task precedent)
- `modules/sports/ports/repositories.py` (`FixtureRepositoryPort`)
- `apps/api/composition.py`, `apps/api/main.py` (news admin endpoints)
- `tests/unit/modules/ingestion/test_celery_tasks.py`, `test_scheduled_retraining_celery_task.py`, `test_scheduled_calibration_celery_task.py`
- Live `dev.db` (`news_sources`, `news_articles` row inspection)

## Current architecture (confirmed)

- **`SyncTrigger` (intelligence)**: `SCHEDULED, MANUAL, RETRY, LIVE_SCHEDULED` — no `ADMIN_MANUAL`/`BACKFILL` yet. `modules.ingestion`'s separate enum already has the full 9-member set including both, established in Milestone 5 for exactly this problem.
- **News sync flow**: `apps/api/main.py:1759` `trigger_news_sync` (admin, per-source) → `NewsIngestionService.sync_source(source_id, now, trigger=MANUAL, on_article_created=...)` → (per genuinely-new article) `IntelligenceEnrichmentOrchestrator.enrich_article` → `EventExtractionService.extract_and_record` (calls Gemini twice: `extract_events` + via `EntityExtractionService.extract_and_link`'s `extract_entities`) → `_classify_and_persist` (confidence tier + availability classification) → feature publish gated on `is_feature_eligible()`.
- **Provider interfaces**: `NewsProviderPort.fetch_articles(source_url, since, cursor)` — `RssNewsProvider` is the only real implementation, registered under `"rss_feed"`. `TextIntelligenceProviderPort` — `GeminiAdapter` is real, resolved per-call by `TextIntelligenceRouter` based on live credential state (never a permanent mock fallback).
- **Source registry**: `news_sources` table, no `is_active` flag — every registered source is implicitly eligible. 9 rows in `dev.db` today; only 1 (BBC) has a genuine RSS feed URL, the other 8 are plain webpage URLs that will fail cleanly (caught, isolated) on a real fetch.
- **Deduplication**: already complete — `NewsArticleModel.url` and `.content_hash` are both DB-level `unique=True, index=True`, backed by an app-level pre-check in `NewsIngestionService._ingest_record`. Nothing new needed.
- **Provenance fields**: `IntelligenceSyncRun` already carries every field Milestone 10 §18 asks for (`trigger, status, started_at, finished_at, items_fetched, items_created, items_duplicate, items_rejected, error_message`, computed `duration_seconds`). `NewsEvent` (Milestone 9) already carries `availability_classification, information_available_at, confidence_tier, resolved_entities`.
- **Entity resolution**: unchanged from Milestone 9 — `EntityExtractionService.extract_and_link` (NER via Gemini + `EntityResolutionService.find_by_alias` against the Knowledge Graph) is the only path that ever populates `resolved_entities`/`affected_entity_refs`; an unresolved mention never becomes a fabricated ref.
- **Feature eligibility / TTL**: `NewsEvent.is_feature_eligible()` (VERIFIED_PRE_MATCH + fully resolved) and `NewsMarketImpactEngine`'s own `ttl_hours` re-check at read time, plus an independent 24h Feature Store online TTL — both already enforce "expired news cannot influence a new prediction." No change needed.
- **Market-specific mappings**: unchanged, three dimensions (`goal_impact`/`clean_sheet_impact`/`btts_impact`), 24 `feature_market_mappings` rows verified in `dev.db` at the end of Milestone 9. Nothing in this milestone touches `news_market_impact_registry.py` or `news_market_impact_engine.py`.
- **Celery factory pattern**: every existing task module (`ingestion`, `predictions`) uses a module-level `_factory: Callable[[], Awaitable[X]] | None`, a `set_X_factory()` setter, and a `_get_X()` that raises `RuntimeError` if unconfigured. Bounded retry convention: `autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3`. Cross-module task modules already import the *shared* `celery_app` instance from `modules.ingestion.infrastructure.celery.celery_app` — established as shared infrastructure, not a module-boundary violation.
- **Configuration loading**: no central settings class for this kind of tunable — every precedent (`LINEUP_PREMATCH_WINDOW_MINUTES`, `STRUCTURED_INTEL_SYNC_WINDOW_HOURS`, Milestone 9's `_VALIDITY_WINDOW_HOURS`) is a module-level constant computed once via a local `_env_int(name, default)` helper reading `os.environ`, duplicated per module rather than shared cross-module (the `modules.intelligence` ↛ `modules.ingestion` boundary already forces this duplication for M9's `_ensure_aware`/`_env_int`).

## Confirmation: no schema migration required

Every field this milestone needs to read or write already exists:
- `IntelligenceSyncRun` — no new columns.
- `NewsEvent`/`news_events` — no new columns (Milestone 9's migration 0041 already added everything).
- `NewsSource`/`NewsArticle` — no new columns; `sync_all_sources` only adds a new loop over `sources.list_all()`, no new persisted field.

**No migration is created in this milestone.**

## Reuse opportunities (confirmed, all reused — none duplicated)

- `NewsIngestionService.sync_source` — reused as-is (extended additively with an optional `since_floor` param, default `None`, for the lookback safety guarantee — existing callers unaffected).
- `IntelligenceEnrichmentOrchestrator.enrich_article` — reused as-is, called with `trigger=SyncTrigger.LIVE_SCHEDULED` from the new scheduled path only.
- `SyncOrchestrator.sync_upcoming_structured_intelligence`'s shape (fixed `trigger` default the task never overrides, per-season fixture-window scoping via `FixtureRepositoryPort.list_by_season`) — mirrored, not imported (module boundary).
- Knowledge Graph alias data (`KGNodeRepositoryPort.get_by_entity_ref` → `.aliases`) — reused for the relevance-filter vocabulary, exactly the same round-trip `NewsMarketImpactEngine._team_contributions` already performs. No second alias system created.
- `_ensure_aware` — replicated locally (5th duplicate of the same established pattern) rather than imported.

## Risks identified

1. **No real worker-startup entrypoint wires any `set_X_factory` today** (pre-existing gap across `ingestion`/`predictions` task modules, not introduced by this milestone) — a real Celery worker process would need this wiring to actually run any scheduled task, including this new one. Out of scope to fix here (same posture Milestone 9 took toward the missing Beat schedule itself); documented as a known limitation in the verification report.
2. **8 of 9 registered news sources have non-RSS URLs** — real, isolated per-source failures on every scheduled run until an operator fixes the source registry. Data-quality issue, not a pipeline defect; `sync_source`'s existing failure isolation already prevents this from affecting other sources.
3. **Relevance filtering is deterministic keyword matching, not semantic** — a team name appearing in an unrelated context (the spec's own "Arsenal supermarket" example) can still false-positive. This is explicitly scoped as a cost pre-filter only, not a resolution step; documented as a known limitation.

## Exact implementation locations

| Change | File |
|---|---|
| `ADMIN_MANUAL`, `BACKFILL` added to `SyncTrigger` | `modules/intelligence/domain/value_objects.py` |
| `sync_all_sources`, `since_floor` param on `sync_source` | `modules/intelligence/application/news_ingestion_service.py` |
| Deterministic relevance filter | `modules/intelligence/application/news_relevance_filter.py` (new) |
| Env-driven config constants | `modules/intelligence/application/news_sync_config.py` (new) |
| Scheduled orchestration (vocabulary build, budget, trigger hardcoding, feature-flag check) | `modules/intelligence/application/scheduled_news_sync_service.py` (new) |
| Celery task | `modules/intelligence/infrastructure/celery/tasks.py` (new) |
| Beat schedule entry | `modules/ingestion/infrastructure/celery/beat_schedule.py` |
| `trigger_news_sync` → `ADMIN_MANUAL` | `apps/api/main.py` |
| Composition wiring | `apps/api/composition.py` |
| Tests | `tests/unit/modules/intelligence/test_news_ingestion_service.py` (extend), new `test_news_relevance_filter.py`, `test_scheduled_news_sync_service.py`, `test_intelligence_celery_tasks.py` |

## Conclusion

Implementation path matches the approved design with no material conflict. Proceeding directly to Phase 3 (implementation) without an additional stop, per the milestone's own "STOP only if the implementation path materially differs" instruction.
