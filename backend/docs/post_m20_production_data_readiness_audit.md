# TitanIQ Post-M20 Production Data Accumulation Readiness Audit

**Phase A — Read-Only Audit. Not a milestone. No code changed, no `dev.db` write, no external API
call, no model trained, no Champion touched.** Every finding below is either a direct file read, a
read-only `dev.db` query (`sqlite3.connect("file:dev.db?mode=ro", uri=True)`), or a local TCP
connect test to the already-running dev-only Redis stand-in — nothing left this machine.

---

## 1–2. NEWS_SYNC_ENABLED / NEWS_BACKFILL_ENABLED — current values

Neither is set in `.env`; both fall through to their code-level defaults:

- **`NEWS_SYNC_ENABLED = False`** (`news_sync_config.py:38`, `_env_bool("TITANIQ_NEWS_SYNC_ENABLED", False)`)
- **`NEWS_BACKFILL_ENABLED = False`** (`news_backfill_config.py:37`, same pattern)

Both defaults are "never fabricate True" by design — confirmed in the source comments. With
`NEWS_SYNC_ENABLED=False`, `ScheduledNewsSyncService.run()` returns immediately at
`scheduled_news_sync_service.py:73-77`: no provider call, no Gemini call, records a `SKIPPED`
summary only. This is why zero external calls occurred anywhere in M19/M20/this audit.

## 3. Gemini credential availability

**Present.** `dev.db.providers` has a `gemini` row (`key='gemini'`, `category='ai'`,
`status='active'`), and `provider_credentials` has one `is_active=1` row for it (plus one rotated
`is_active=0` row — normal rotation history, not a problem). `TextIntelligenceRouter._resolve()`
(`text_intelligence_router.py:51-61`) checks exactly `provider.is_usable()` (→
`status is ProviderStatus.ACTIVE`, `admin/domain/entities.py:62-63`) plus a non-empty
`usable_credentials` list — both conditions are satisfied today. **If scheduled sync ran right
now, it would use the real Gemini adapter, not the mock.** No credential value was read or logged.

## 4. RSS provider registration

**9 sources registered** in `news_sources` (all `source_type='rss_feed'`, the only type
`NewsIngestionService._resolve_provider` currently has a real adapter for —
`composition.py:642-654`, wired to `RssNewsProvider()`, no credential required for RSS itself).

**Finding worth flagging**: of the 9, only 4 are genuinely football-relevant (BBC Sport Football,
ESPN Sport, 90mins, theGuardian) — the other 5 (ESPN NBA, Reuters basketball, NYTimes/Athletic
NBA, Athletic MLB, MLB.com) target other sports and would never surface an article the
football-relevance vocabulary matches. More importantly: **3 of the 4 football-relevant URLs are
plain webpage URLs, not RSS/Atom feed endpoints** — `https://africa.espn.com/football/`,
`https://www.90min.com/`, `https://www.theguardian.com/football` are HTML pages, not `.xml`
feeds. Only `https://feeds.bbci.co.uk/sport/football/rss.xml` (BBC) looks like a real,
fetchable RSS feed URL. `RssNewsProvider` parses responses with `xml.etree.ElementTree`
(`rss_news_provider.py:9`) — feeding it an HTML page would raise a parse error (a per-source
failure, isolated by `sync_all_sources`'s existing per-source try/except, not a crash of the
whole run) or silently return zero items, not fabricate anything. **This is a real, pre-existing
data-quality gap unrelated to M20**: only one of the nine registered sources is verified likely to
actually work as an RSS feed today.

## 5–8. Celery worker / Beat / Redis / M11 bootstrap

- **Redis**: reachable — confirmed via a local TCP connect test to `127.0.0.1:6379`
  (`TITANIQ_REDIS_URL` in `.env`). This is the dev-only `fakeredis.TcpFakeServer` stand-in
  (`scripts/run_local_fake_redis.py`), not real Redis — it requires a human to keep it running
  (it died once already this session and had to be manually restarted). **This is a real
  operational gap for anything beyond this single dev session/machine**: there is no supervisor,
  no auto-restart, and no persistence guarantee for this process.
- **Celery worker bootstrap (M11)**: `apps/worker/bootstrap.py` is real and complete —
  `validate_environment()` checks `TITANIQ_DB_URL`/`TITANIQ_REDIS_URL`/`TITANIQ_ENCRYPTION_KEY`
  (all three present in `.env`), `import_task_modules()` registers all 4 task modules,
  `register_factories()` wires all 5 required factories (including
  `scheduled_news_sync` → `ScheduledNewsSyncService`), `validate_factory_registry()` fails closed
  if any are missing. Sound, unchanged since M11.
- **Celery Beat**: `sync-scheduled-news-football-epl` entry exists in `beat_schedule.py:189-193`,
  correctly targeting task `intelligence.sync_scheduled_news` on a `NEWS_SYNC_SCHEDULE_INTERVAL_SECONDS`
  cadence. The companion structured-intelligence entry (`sync-upcoming-structured-intelligence-football-epl`)
  is also present, registered under the already-validated `orchestrator` factory.
- **No worker or Beat process is currently running** in this dev environment (this is a code/config
  audit, not a running-process audit — starting either is an operational decision, correctly out
  of scope for a read-only Phase A).

## 9. M10 scheduled news task

`intelligence.sync_scheduled_news` (`modules/intelligence/infrastructure/celery/tasks.py:63-64`)
deliberately has no `trigger` parameter — it calls `ScheduledNewsSyncService.run()`, which
internally hardcodes `SyncTrigger.LIVE_SCHEDULED` (`scheduled_news_sync_service.py:89,122`) with
no way for a caller to override it. This is the only production code path that can ever produce
that trigger value — confirmed unchanged from M16/M19/M20's findings.

## 10. Relevance filter ordering

**Confirmed strictly before Gemini**, read directly in `scheduled_news_sync_service.py`:
`relevance.is_relevant(...)` filters candidates (line 108) → results are sorted and hard-truncated
to `NEWS_SYNC_MAX_ARTICLES_PER_RUN` (lines 116-118) → **only then** does `enrichment.enrich_article(...)`
(the Gemini-calling step) run, per surviving article (line 122). No article reaches Gemini without
passing the deterministic filter first.

## 11. Gemini cost controls

All conservative, all applied pre-Gemini (`news_sync_config.py`):
- `NEWS_SYNC_MAX_ARTICLES_PER_RUN = 20` — hard cap, applied after filtering, before any Gemini call.
- `NEWS_SYNC_LOOKBACK_HOURS = 48` — bounds how far back a source's fetch window reaches.
- `NEWS_SYNC_INTERVAL_SECONDS = 900` (15 min) — Beat cadence; combined with the 20-article cap,
  a predictable ceiling of 40 Gemini calls/15min (2 calls/article: extract_events + extract_entities,
  per the config's own comment) an operator can reason about before raising it.
- `NEWS_SYNC_FIXTURE_WINDOW_HOURS = 168` (7 days) — bounds the relevance-vocabulary lookahead.
- Per-article enrichment failures are caught and isolated (`scheduled_news_sync_service.py:120-126`)
  — one bad article/Gemini error does not abort the run or corrupt the summary.

## 12–13. Provenance classification / VERIFIED_PRE_MATCH generation path

Unchanged, re-confirmed this audit: `news_provenance.py:70-71`'s strict
`trigger is not SyncTrigger.LIVE_SCHEDULED` check is the sole gate; `ADMIN_MANUAL`/`BACKFILL`
can never produce `VERIFIED_PRE_MATCH`; `information_available_at < fixture.scheduled_at` is
enforced with strict inequality; `HISTORICALLY_RELEVANT` never bypasses `is_feature_eligible()`.
No code in `modules.intelligence`/`modules.ingestion` was touched by this audit.

## 14. TrainingPreflightService

Fully operational — built in M19, exercised live in M20, exercised again this audit
(`scripts/run_training_preflight.py`). No changes since M20's close.

## 15. Current readiness of all 14 trained football markets

Re-ran live against `dev.db` this audit: **0/14 READY**, identical to M20's close — no market has
moved, because no `VERIFIED_PRE_MATCH` observation has been produced since M20 finished (no sync
has run; `NEWS_SYNC_ENABLED` is still `false`).

---

## Summary Verdict

| Prerequisite | Status |
|---|---|
| NEWS_SYNC_ENABLED | `false` (correct current default) |
| NEWS_BACKFILL_ENABLED | `false` (correct, must stay this way) |
| Gemini credential | **Ready** — active provider + active credential in `dev.db` |
| RSS sources | **Partially ready** — 9 registered, only ~1 (BBC) looks like a real feed URL |
| Redis | **Reachable now**, but dev-only/unsupervised — a real operational gap |
| Celery worker bootstrap (M11) | **Ready** — 5/5 factories wire correctly, fail-closed validated |
| Celery Beat schedule | **Ready** — both news and structured-intel entries present |
| Relevance filter → Gemini ordering | **Correct** — filter and hard cap both precede any Gemini call |
| Cost controls | **Present and conservative** |
| Provenance/eligibility gates | **Unchanged, intact** |
| TrainingPreflightService | **Operational** |
| Market readiness | **0/14 READY** (unchanged since M20) |

**Nothing here is a code defect.** The architecture prerequisites for turning
`NEWS_SYNC_ENABLED` on are largely in place (Gemini credentialed, worker/Beat wiring correct, cost
controls conservative). Two real, non-blocking-but-worth-fixing gaps surfaced: (a) most of the 9
registered RSS sources are not real feed URLs and would likely fail or return nothing, and (b) the
local Redis stand-in has no supervision/persistence beyond this session.

**STOPPING HERE per the master command's Phase A protocol. No code was changed, `dev.db` was not
written to, no external API was contacted, no model was trained, no Champion was modified. Waiting
for explicit approval before Phase B (proposed design for any of: fixing the RSS source URLs,
addressing Redis supervision, or actually enabling `NEWS_SYNC_ENABLED`).**
