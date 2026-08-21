# TitanIQ — Production Readiness Audit

**Date:** 2026-08-21
**Scope:** Read-only audit of the existing repository (backend, frontend, infrastructure). No code, config, credentials, or infrastructure were changed in the course of this audit.
**Method:** Full secrets scan of tracked source + git history (performed directly), plus nine parallel focused audits of backend architecture/DB, Redis/Celery/Beat, provider safety, ML/Champion governance, Gemini/Knowledge Graph/freshness, auth/security, billing/webhooks, frontend build/SEO/legal, and infrastructure/observability. Every finding below cites a concrete file:line; anything that could not be verified from source alone is labeled as such rather than guessed.

---

## 0. Executive Summary

**Overall verdict: NOT PRODUCTION READY.** Two different classes of gap, and they should not be conflated:

1. **The application layer is materially more mature than a typical pre-launch codebase.** Domain/application/infrastructure layering is real and consistent, migrations are clean and additive, the provider-integration layer (credential vault, quota gating, circuit breaker, deterministic reconciliation) is genuinely production-grade, Champion/Challenger governance and leakage/parity gates are real and enforced (not just documented), Supabase JWT verification, CORS, security headers, and admin RBAC are all correctly implemented, and Flutterwave webhook signature verification is real and idempotent. This is not "fabricated production readiness" — it's real, working code with real safety rails in most of the places that matter most (never fabricating sports data, never letting Gemini alter a prediction, never trusting a client-supplied plan tier).

2. **The deployment/infrastructure layer does not exist yet, and the project's own prior documentation already says so.** There is no Dockerfile, no docker-compose file, no CI/CD pipeline, no correlation-ID logging, no metrics/APM, no alerting, no environment separation (dev/staging/production is a single flat `.env`-driven config), no backup strategy, and no documented multi-worker production server invocation anywhere in the repo. `backend/docs/deployment.md` and `backend/docs/security.md` both independently describe this as **known, tracked, not-yet-started work gated behind "Milestone 20"** — this audit did not discover a hidden gap so much as confirm an already-acknowledged one.

Given (2), **Sections 32–38 of the original spec (staging deployment, staging E2E test, production deployment) cannot be attempted from this repository as it stands today** — there is nothing to containerize/deploy yet, and doing so would require infrastructure decisions (hosting provider, domain, DNS, secrets manager) that are the user's to make, plus real credentials this environment does not have. That is not a tooling limitation to route around; building a deployment pipeline and then deploying it in the same pass, without the user choosing where it runs, would be exactly the kind of fabricated/unauthorized production action the spec's own Section 44 (Strict Stop Conditions) forbids implicitly by demanding real, verified infrastructure.

**What this document is:** the real, evidence-based Section 1 audit the spec asked for first, plus a prioritized punch list. It is the honest input needed to scope the infrastructure work in Sections 2–31 before anyone can responsibly attempt Sections 32+.

---

## 1. Backend Architecture, Database & Migrations

| # | Item | Verdict |
|---|---|---|
| 1 | Domain/application/infrastructure layering | **PASS** |
| 2 | Database engine (SQLite vs Postgres) | **PARTIAL** |
| 3 | Connection pooling | **FAIL** |
| 4 | Migrations (forward-compat, single head) | **PASS** |
| 5 | Indexes/constraints/FKs | **PASS** |
| 6 | Transaction boundaries | **PASS** |
| 7 | Concurrent workers / locking | **PARTIAL** |

`backend/modules/*` genuinely separates `domain/`, `application/`, `infrastructure/`, `ports/` across all 13 modules. `backend/apps/api/composition.py` is a real composition root — repositories are constructed per-request off a request-scoped `AsyncSession`, not global singletons (except the engine/session factory themselves, which are `@lru_cache`d, and the FastAPI `lifespan` hook does no resource setup/teardown, `main.py:118-123`).

**Database:** today the app runs on **SQLite** (`.env:21` → `TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db`). Postgres support is genuinely *coded* — dialect-generic `Uuid`/`JSON` types, a real `pool_size`-configured Postgres branch in `modules/sports/infrastructure/persistence/database.py:51-69`, `asyncpg` declared as a dependency, dialect-agnostic `alembic/env.py` — but **has apparently never been exercised end-to-end from this repo**: no `postgresql://` URL appears anywhere outside `tests/integration/conftest.py`, and no doc/CI evidence shows migrations or the app ever running against a live Postgres instance.

**Connection pooling gap:** only `pool_size` is configured; **no `pool_pre_ping`, no `max_overflow`** anywhere in application code (verified by grep — only library-internal hits in `.venv`). Without `pool_pre_ping`, a Postgres failover or idle-connection timeout in production surfaces as a runtime error instead of transparent recycling.

**Migrations:** `alembic heads` reports a single head (`0045`), 46 version files. Sampling the 5 most recent plus a grep pass found every forward `upgrade()` operation additive (`add_column`, `create_table`, `create_index`); `drop_table`/`drop_column` only appear inside `downgrade()` in the sampled set (not exhaustively verified across all 46).

**Transactions:** centralized — `get_session()` (`composition.py:328-332`) commits once after the route handler returns; zero repositories call `session.commit()` themselves. The Celery worker path is deliberately different (`AUTOCOMMIT` isolation, documented tradeoff, `apps/worker/bootstrap.py:175-197`) since a long-lived worker has no natural request boundary.

**Locking:** no `SELECT FOR UPDATE`/Postgres advisory locks anywhere — coordination is entirely Redis-based (`RedisDistributedLock`). A `version` column exists on some models but is a plain incrementing integer in application code, not wired as SQLAlchemy's `version_id_col` — it provides audit history, not actual optimistic-concurrency enforcement.

---

## 2. Redis, Celery & Celery Beat

| # | Item | Verdict |
|---|---|---|
| 1 | Redis config (env-driven, DB isolation) | **PARTIAL** |
| 2 | Task inventory vs spec's list | **PARTIAL** |
| 3 | Retry policy | **PASS** |
| 4 | Idempotency | **PARTIAL** |
| 5 | Task timeouts | **PARTIAL** |
| 6 | Dead-letter/error handling | **PARTIAL** |
| 7 | Structured logging in tasks | **FAIL** |
| 8 | Celery Beat schedule + retraining gating | **PASS** |
| 9 | Distributed locks | **PASS** |

`REDIS_URL` is env-driven (`RedisSettings`, `env_prefix="TITANIQ_REDIS_"`), but Celery's broker/backend resolution **silently falls back to hardcoded `redis://localhost:6379/0`** if settings resolution throws (`celery_app.py:21-28`) — a misconfigured production env fails silently rather than loudly. Broker, result backend, feature-store cache, dead-letter list, and distributed locks all share **one Redis DB** (no index/isolation split).

**Real, wired tasks (16):** country/team/fixture/live-fixture/upcoming-fixture/completed-fixture/standings/standings-alt/odds/team-statistics sync, structured-intelligence sync (folds injuries/lineups/transfers into one task), scheduled news sync, retraining/calibration/calibration-validation checks, provider health checks.

**Not real, despite being implied by the spec's task list:** prediction generation is **not a Celery task at all** — `PredictionEngine.generate()` is synchronous, request-time. No notification/email task exists anywhere (zero grep matches). Injuries/lineups/transfers are not separate tasks (folded into one).

Retry policy is uniform and real: `autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=300, max_retries=3` on every task, `task_acks_late=True` globally. **No `soft_time_limit`** anywhere (only a global 600s hard `task_time_limit`) — a heavy retraining task and a cheap `sync_countries` call share the same ceiling with no graceful-shutdown opportunity.

**Idempotency:** fixture/entity sync is genuinely idempotent — real `UniqueConstraint`s on `(provider, external_id, entity_kind)` and `(sport_code, entity_kind, scope_key)`, real `upsert()` repository methods, plus a Redis lock preventing concurrent duplicate runs of the same sync scope. **Prediction generation has no equivalent** — the `predictions` table has no unique constraint on `(market_id, subject_ref)`; re-invoking generation for the same fixture/market creates a new row rather than upserting.

**Dead-letter queue is real but has no operator surface**: a `@task_failure.connect` handler pushes to a capped Redis list (`dlq:sync_tasks`) once retries are exhausted, with a reader function — but nothing in `modules/admin` calls that reader, and no router exposes it. Failures are recorded but currently invisible short of querying Redis directly.

**Structured logging: zero.** Grepped every `**/celery/tasks.py` file across all four modules plus `sync_orchestrator.py` — no `logging`, `structlog`, or `print` calls anywhere in the task layer. Errors surface only via the dead-letter handler and Celery's own default logging.

**Beat schedule** (17 real entries, `beat_schedule.py:88-207`) is sensible and matches product needs: live fixtures every 30s, standings hourly, structured intelligence/news every 15 min, provider health every 5 min, retraining/calibration checks every 6h/1h. Retraining is genuinely gated, not timer-driven: `ScheduledRetrainingOrchestrator._check_and_retrain` calls `should_retrain()`, then a full `TrainingPreflightService.check()` (sample size, leakage, parity, chronological holdout ≥45 samples) before any training happens, and only auto-promotes in the narrow "market never had a Champion" bootstrap case — otherwise promotion stays a human gate.

Distributed locking (`RedisDistributedLock`, `SET NX EX`) is real and wired into the sync path, though not into the retraining/calibration/provider-health Beat tasks (those assume a single Beat scheduler instance, which is an infra property, not verifiable from source).

---

## 3. Provider Safety

| # | Item | Verdict |
|---|---|---|
| 1 | Credential management | **PASS** |
| 2 | Quota tracking (proactive) | **PASS** |
| 3 | Client-side rate limiting | **PARTIAL** |
| 4 | Timeout config | **PARTIAL** |
| 5 | Circuit breaker | **PASS** |
| 6 | Fallback / provider priority | **PASS** |
| 7 | Provider outage behavior | **PASS** |
| 8 | Malformed response handling | **PASS** |
| 9 | Duplicate fixture reconciliation | **PASS** |
| 10 | Provenance | **PARTIAL** |

This is the most mature subsystem in the audit. Credentials live in a DB-backed vault, Fernet-encrypted at rest (`TITANIQ_ENCRYPTION_KEY`, required to fail-fast at startup), masked on every display path. Quota is tracked proactively (daily+monthly counters) and enforced **before** a call is made (`SportsProviderRouter._execute` → `quota_engine.should_throttle`), not just reacted to after a 429. A real closed/open/half-open circuit breaker is genuinely wired into the provider call path (not a standalone unused class), with a documented tradeoff that its state is in-memory/per-process (won't share across multiple Celery workers). Fallback to a supplementary provider (e.g. TheSportsDB) is explicit opt-in, and supplementary-provider scores never silently overwrite an authoritative provider's data. Outage behavior is honest throughout: failures are recorded and the sync run marked FAILED, missing dependent entities are rejected with a logged reason — nothing is fabricated or interpolated. Duplicate-fixture reconciliation is deterministic (provider+external_id primary match; a narrow, explicitly-opt-in fuzzy team/date fallback that refuses to guess on ambiguous matches).

Two real, minor gaps: no independent rate limiter beyond quota-gating/circuit-breaker/backoff (acceptable but worth a hard cap), and HTTP timeouts are single blanket values rather than split connect/read timeouts. Provenance is universal for *source* (every entity carries `provider_refs`) but `observed_at`/`fetched_at` timestamps are only present on the structured-intelligence entities (injuries/transfers/lineups) that the Milestone 5 provenance work targeted — not on Team/Fixture/Player, which rely on a version counter instead.

---

## 4. ML Prediction Engine & Champion Governance

| # | Item | Verdict |
|---|---|---|
| 1 | Model artifact storage | **PARTIAL** |
| 2 | Model metadata completeness | **PARTIAL** |
| 3 | Champion/Challenger/Retired states | **PASS** |
| 4 | Promotion gates | **PARTIAL** |
| 5 | Rollback to previous Champion | **PASS** |
| 6 | Goal/count vs correct-score vs classifier architecture separation | **PASS** |
| 7 | API field separation (goals ≠ score, confidence ≠ probability, contribution ≠ feature value) | **PASS** |
| 8 | Training/inference parity + leakage checks | **PASS** |
| 9 | Production inference gate | **PARTIAL** |

**Real production blocker:** the only wired `ModelArtifactStorePort` implementation is `LocalFilesystemArtifactStore`, writing to a relative `.model_artifacts` directory, hardcoded in `composition.py:1082-1083` with no env-based swap. A `ModelArtifactModel` registry table exists (`storage_ref`/`content_hash`/`size_bytes`) but nothing ever writes to it — dead schema. **Artifacts will not survive a container restart or be shared across multiple instances** — this must be solved (object storage adapter) before any multi-instance/serverless deployment.

Champion/Challenger/Retired is a real, enforced enum with a real registry service (`promote_to_challenger`, `promote_to_champion` atomically retiring the prior champion, single-champion invariant enforced). Real rollback exists (`ModelRegistryService.rollback()` reinstates the most-recently-retired model; `ModelLoaderService.invalidate()` evicts the stale cached artifact) — no manual DB edit required.

Promotion *gates* are real (sample-size threshold, chronological/out-of-sample validation, feature parity, leakage safety, dataset-reproducibility double-build with content-hash comparison, baseline comparison against tagged GLM/logistic candidates) but **`promote_to_champion` itself does not mechanically enforce that a favorable `ChallengerEvaluation` exists** — it only checks lifecycle state plus an unvalidated human `approved_by` string. The gating is real but currently relies on the caller (Ops Center) wiring it correctly, not the service itself refusing an ungated promotion.

Architecture separation is genuinely real, not one model stretched across markets: `FootballGoalsPoissonAdapter` (goal/count + correct-score, closed-form Poisson derivation) is distinct from the gradient-boosting/classical classifiers (`LightGBMAdapter`, `XGBoostAdapter`, `CatBoostAdapter`, `SklearnAdapter`) used for win/draw/loss and BTTS. `expected_home_goals`/`expected_away_goals`, scoreline probability, selection probability, confidence, and per-feature attribution all serialize as genuinely separate fields in the prediction API response (naming differs slightly from the spec's suggested field names, but nothing is conflated).

**Most important gap:** the production inference chokepoint (`PredictionContextBuilder.build()`) correctly refuses to generate when the market isn't in production or no Champion exists (structured diagnostic, not fabrication). But **artifact-load failure is not a hard gate** — `PredictionEngine._resolve_predictor()` catches any exception from `ModelLoaderService.load()` and silently falls back to a generic weighted-formula predictor rather than surfacing a diagnostic. This is a deliberate "never break generation" design choice per the code's own comments, but it means a corrupted/missing Champion artifact degrades prediction quality **silently**, with no signal to the caller that a fallback happened. This directly matters for Section 10 of the original spec ("If any mandatory gate fails: DO NOT generate a prediction... never fall back to... a fabricated/generic prediction") — as built today, that rule is violated for this one failure mode.

---

## 5. Gemini, Explainability & Knowledge Graph

| # | Item | Verdict |
|---|---|---|
| 1 | Pipeline order (Model → Attribution → Evidence → Gemini) | **PASS** |
| 2 | Gemini output schema validation | **PASS** (structured paths) / **PARTIAL** (other adapter methods) |
| 3 | Gemini cannot alter the prediction | **PASS** |
| 4 | Gemini failure handling | **PARTIAL** |
| 5 | Mock/fallback disclosure | **PARTIAL** |
| 6 | Knowledge Graph node/edge coverage | Real, but worse than previously assumed |
| 7 | KG provenance/temporal fields | **PARTIAL** |
| 8 | Live-context freshness states | **PARTIAL** |
| 9 | UI-facing staleness signal | **PARTIAL** |

The core safety property holds structurally: Gemini's schema (`FootballExplanationSchema`, `extra="forbid"`) deliberately has no field it could use to overwrite a verified attribution value — only prose fields exist. Numeric `key_reasons`/`counter_signals` are always rebuilt from the real attribution result; only narration text is merged from Gemini's response. Football-path failure handling is robust (`ValidationError`/`JSONDecodeError`/generic exception all caught, falls through to an explicit `UNAVAILABLE` status without touching the underlying `Prediction`). The **generic** (non-football) explainability path is less hardened — no try/except around the Gemini call, so an unanticipated exception there can fail the entire prediction-generation request, not just the explanation.

**Real product-honesty gap:** when Gemini quota is exhausted or credentials are missing, the system falls back to `mock_gemini_adapter.py` — and that adapter's own docstring states it *deliberately avoids labeling output "mock"* in user-facing text. There is no `is_mock`/`provider_source` field anywhere on `FootballExplanation` or `ContextualReview`. **The frontend has no way to distinguish a real Gemini narration from a deterministic mock one.** Given this project's explicit "never fabricate" ethos, this is worth a real decision: either disclose it, or confirm this is an intentional product choice.

Knowledge Graph coverage has **grown less complete since it was last checked**, not stayed flat: 13/47 `NodeType` members have real writers (was reported as 13/42 previously — the enum grew without new writers), 7/33 `EdgeType` members (was 7/30). `KGNode.valid_from`/`valid_to` don't exist on nodes at all (only on edges), and edge `valid_from` is stamped at ingestion time, not true event time, confirming the earlier finding that `EVENT_TIME < MATCH_KICKOFF` cannot be proven from the KG itself.

Freshness exists as a real 3-state (`CURRENT`/`STALE`/`UNKNOWN`) feature-level continuous score, not the spec's proposed 4-state FRESH/AGING/STALE/UNAVAILABLE per-evidence-item classification. `EvidenceItem`s do carry real `published_at`/`retrieved_at` and are cutoff-filtered with tracked rejection reasons, but no freshness label is computed per item. The public prediction response does serialize `confidence.feature_freshness` (raw score) and `data_freshness` (timestamp) — so a signal reaches the frontend, but as raw numbers the frontend must interpret itself, not a pre-computed status label.

---

## 6. Authentication & Security

| # | Item | Verdict |
|---|---|---|
| 1 | Auth provider (Supabase) | **PASS** |
| 2 | Backend JWT verification | **PASS** |
| 3 | Session/logout | **PASS** |
| 4 | Rate limiting coverage | **PARTIAL** |
| 5 | CORS | **PASS** |
| 6 | Security headers | **PASS** |
| 7 | Input validation | **PASS** |
| 8 | SQL injection surface | **PASS** |
| 9 | XSS surface | **N/A** (no `dangerouslySetInnerHTML` anywhere) |
| 10 | Admin authorization | **PASS** |
| 11 | Secrets never logged | **PASS** |

This is the strongest-audited domain alongside provider safety. Supabase JWTs are verified server-side against the real, rotating Supabase JWKS endpoint (signature, audience, issuer, expiry) — not trusted blindly, not checked against a static shared secret. A separate offline/PAT auth path exists purely for testing, disabled by default (`TITANIQ_ENABLE_OFFLINE_AUTH=false`, 404s when off). CORS is a real env-driven allowlist, never a wildcard. Security headers (CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy) are set globally with Swagger UI correctly excluded. Every POST/PATCH body is a typed Pydantic model; no raw-body bypass found. No string-interpolated SQL found anywhere (ORM/Core parameterized throughout). Admin routes are gated server-side via a real `require_role(ADMINISTRATOR)` dependency on every route, not just hidden client-side, with permission denials written to an audit trail.

**Real gap:** a working Redis-backed rate limiter exists and is applied to login, register, and prediction generation — but **the entire public marketing API and every admin endpoint have zero rate limiting**. The public API has only an in-process TTL cache (self-documented in its own code as a known gap), and admin endpoints rely solely on RBAC with no throttle against credential-stuffing or scripted abuse. This is the single most actionable security gap found.

Minor defense-in-depth note: the Gemini API key is passed as a URL query parameter rather than an Authorization header — not a current logging leak (no logging exists in that module), but worth changing if any HTTP tracing/proxy tooling is added later.

---

## 7. Billing & Webhooks

| # | Item | Verdict |
|---|---|---|
| 1 | Payment provider | **PASS** (Flutterwave only, no Stripe/Paystack) |
| 2 | Plans/pricing (DB-driven, not frontend-trusted) | **PASS** |
| 3 | Checkout flow | **PASS** (real orchestration, not a stub) |
| 4 | Webhook signature verification | **PASS** |
| 5 | Idempotent webhook processing | **PASS** (minor race caveat, not a duplication risk) |
| 6 | Entitlement updates (transactional) | **PASS** |
| 7 | Full lifecycle coverage (success/fail/renew/cancel/upgrade/downgrade) | **PARTIAL** |
| 8 | Frontend trust boundary | **PASS** |
| 9 | Billing ledger/history | **PARTIAL** |

The webhook path is genuinely solid: HMAC-SHA256 signature verification with constant-time comparison before anything is trusted, a real DB-level unique constraint on `(provider, event_id)` preventing duplicate processing, and entitlement updates happen inside the same request-scoped transaction as the idempotency check — a failure anywhere rolls the whole thing back, so no partial state is possible. No endpoint anywhere trusts a plan/tier value sent directly from the frontend; `plan_key` is only ever used to look up a server-side `Plan` row.

**Real gap, most important finding in this domain:** `charge.failed` webhooks are verified and marked processed, then **silently dropped** — no status update, no user notification, no retry hook. `SubscriptionStatus.PAST_DUE` is defined but never assigned anywhere in the codebase — there is no renewal/expiry handling at all; `current_period_end` is stored but nothing reads it to expire or downgrade a subscription. Cancellation exists but only as an admin-manual action, not a webhook-driven flow. There is also no real billing ledger recording actual charged amounts/currency over time — only a webhook-event dedup table and a generic audit log entry on subscribe/cancel.

Separately (noted but not this section's finding): entitlement-checking (`BillingService.has_feature`) is implemented but not yet called from any actual prediction/ML feature route — today, no route enforces plan-gating in either direction. Worth flagging before monetization is meaningfully "live."

---

## 8. Frontend Production Build, SEO & Legal

| # | Item | Verdict |
|---|---|---|
| 1 | Production build (`tsc -b`, `vite build`) | **PASS** |
| 2 | Environment variables | **PARTIAL** |
| 3 | localhost/mock/dummy/fake/placeholder scan | **PASS** (one real risk flagged) |
| 4 | SEO (per-route title/meta/OG/canonical) | **PASS** |
| 5 | sitemap.xml / robots.txt | **FAIL** |
| 6 | Legal/trust pages | **PASS** |
| 7 | Error/loading states | **PASS** |
| 8 | Responsive design | **PASS** |

Both `npx tsc -b` and `npm run build` complete cleanly — zero type errors, a working `dist/` with a PWA service worker. Non-blocking build warnings: a 1.53 MB unsplit main chunk, and two pages statically+dynamically imported in a way that defeats code-splitting for them specifically.

Every real `mock`/`fake`/`dummy` hit in the frontend source is either a comment describing an anti-pattern being *avoided*, legitimate `placeholder=` form-input copy, or one explicitly disclosed admin-facing stub (Community Intelligence, documented as "mock-only by design until a live platform provider exists, ADR-008"). SEO is real and per-route (custom `Seo` component setting title/description/canonical/OG/Twitter/JSON-LD across 37 pages), not a single static index.html title. All 14 legal/trust pages exist, are routed, are footer-linked, and contain real TitanIQ-specific content (not placeholder text) — including an explicit, correctly-worded disclaimer that TitanIQ is "a sports intelligence platform, not a betting operator, tipster service, or gambling advisor."

**Two real gaps:** (1) `frontend/src/lib/env.ts:9` — `VITE_API_BASE_URL` silently falls back to `http://localhost:8000` if unset, unlike the Supabase env vars two lines below it which use a `required()` guard that throws. A production build with this var accidentally omitted would ship silently pointing at localhost. (2) **No `robots.txt` or `sitemap.xml` exists anywhere in `frontend/public/`** — nothing currently tells crawlers to exclude the 30+ private `/app/*` routes from indexing, and there's no sitemap for the public marketing pages either.

---

## 9. Infrastructure, Deployment & Observability

| # | Item | Verdict |
|---|---|---|
| 1 | Dockerfiles | **FAIL** (absent) |
| 2 | Other deployment config (CI/CD, platform configs) | **FAIL** (absent) |
| 3 | Health check endpoints | **PARTIAL** (exists, but shallow) |
| 4 | Structured logging / correlation IDs | **FAIL** |
| 5 | Observability / metrics (APM) | **FAIL** |
| 6 | Alerting | **FAIL** |
| 7 | Rate limiting infra | **PARTIAL** (custom, partially applied — see §6) |
| 8 | Environment separation (dev/staging/prod) | **FAIL** |
| 9 | Backup strategy | **FAIL** (documented as not started) |
| 10 | Production ASGI server invocation | **FAIL** (no docs, no multi-worker config) |

This is the domain with the fewest passes, and it is **known, already-documented technical debt**, not a hidden discovery: `backend/docs/deployment.md` states outright that the current posture is "Development/staging deployment against the live `titaniq` Supabase project" and that the "Production launch checklist... remains gated at Milestone 20." `backend/docs/security.md` independently confirms backup strategy, RPO/RTO targets, and restore drills are "Not started."

Concretely: no `Dockerfile` anywhere in the repo (the app runs today as a bare `uvicorn apps.api.main:app --port 8000` process, no `--workers` flag, no gunicorn). No `docker-compose*.yml`. No `.github/` directory — zero CI/CD workflows of any kind. `GET /api/v1/health` exists but is a static `{"status": "ok"}` with no DB/Redis dependency check — no `/liveness`/`/readiness` routes exist. No request/correlation ID is generated or attached anywhere (grep for `structlog` returns zero hits in `backend/`; logging is plain stdlib `logging` throughout). No APM/metrics library (`prometheus_client`/`opentelemetry`/`sentry_sdk`) appears in `pyproject.toml` or anywhere in code — despite `docs/architecture.md` describing full OpenTelemetry tracing as an intended target "from Milestone 2 onward," none of it is implemented. No alerting integration of any kind (zero matches for PagerDuty/Slack-webhook/ops-email patterns). Configuration is a single flat `.env`-driven setup with no `ENVIRONMENT`/`APP_ENV` branching anywhere — dev, staging, and production are not distinguished by the code today, only by which `.env` file happens to be loaded.

The one bright spot: a working custom rate-limiting primitive already exists (`backend/apps/api/rate_limit.py`, Redis `INCR`+`EXPIRE`-based, fails open on Redis unavailability) and is partially applied — it just isn't a recognizable off-the-shelf library, and (per §6) isn't applied broadly enough yet.

---

## 10. Consolidated Punch List (priority order)

**Critical — block any production deployment:**
1. No containerization, CI/CD, or deployment configuration exists at all (Dockerfile, docker-compose, or platform-specific config). *(§9)*
2. No backup/restore strategy exists for the database — explicitly "not started" per the project's own docs. *(§9)*
3. No environment separation — dev/staging/production is one flat config today. *(§9)*
4. Model artifacts are local-filesystem-only; they will not survive a restart or be shared across instances in any real deployment. *(§4)*
5. Public marketing API and every admin endpoint have zero rate limiting. *(§6)*

**High — real product-correctness or security gaps, independent of deployment:**
6. Artifact-load failure silently falls back to a generic predictor instead of surfacing a diagnostic — violates the "never fall back to a fabricated/generic prediction" rule for this one failure mode. *(§4)*
7. Failed-payment and renewal/expiry webhooks are silently no-op'd; `PAST_DUE` is defined but never used. *(§7)*
8. No disclosure anywhere when a Gemini explanation is actually the deterministic mock fallback. *(§5)*
9. No structured/correlated logging in any Celery task, and no correlation IDs anywhere in the API. *(§2, §9)*
10. No `robots.txt`/`sitemap.xml`; `VITE_API_BASE_URL` fails silently into a localhost default if omitted from a production build. *(§8)*

**Medium:**
11. `pool_pre_ping`/`max_overflow` not configured for the (currently unexercised) Postgres path. *(§1)*
12. Prediction generation has no idempotency key — re-invocation creates duplicate rows rather than upserting. *(§2)*
13. Dead-letter queue is recorded but has no operator-facing surface (nothing reads it). *(§2)*
14. No APM/metrics, no alerting integration of any kind. *(§9)*
15. Postgres has never actually been exercised end-to-end from this repo despite being coded. *(§1)*

---

## 11. What Would Actually Need to Happen Before Sections 32–45

The original spec's Sections 32 onward (staging deployment through final production sign-off) assume a deployable artifact and chosen infrastructure. Neither exists yet. Before any of that is attemptable:

- **A hosting decision** (the user's to make: which provider, budget, region) for the API, workers, Beat, Postgres, and Redis.
- **A Dockerfile** for the backend (and a build step for the frontend static assets) — none exists today.
- **A real Postgres instance** to finally exercise the already-coded Postgres path end-to-end, since it has never been run.
- **An object-storage adapter** for model artifacts (the `ModelArtifactStorePort` is ready for this; only the adapter and the swap in `composition.py` are missing).
- **A domain and DNS** the user controls, plus a decision on TLS termination (managed by the host, or a reverse proxy the user configures).
- **Real backup automation**, tested with an actual restore, before any real user data exists in the production database.
- **Basic observability** (structured logs with correlation IDs, at minimum) — running blind in production, with no alerting and no metrics, means any incident is diagnosed after the fact from raw application logs alone.

None of this is unusually hard relative to the application code already in place — the hard, product-specific parts (never fabricating data, real leakage/parity gates, real provider safety) are already done well. What's missing is generic, well-understood infrastructure work that has simply not been started yet, exactly as the project's own prior docs already say.
