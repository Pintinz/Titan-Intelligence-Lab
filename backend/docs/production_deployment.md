# TitanIQ — Production Deployment on Render

**Status of this document:** the deployment *plan and configuration* are real and ready to execute.
Actual execution against a live Render account has **not** happened — this environment has no
Render credentials, no Docker daemon, and no way to reach a live Render API. Everything below is
either (a) real, verified-locally configuration, or (b) explicitly marked as requiring you to run
it from the Render dashboard, with the exact steps to do so.

---

## 1. Architecture

```
                    USERS
                      |
                      v
            titaniq-frontend (Render Static Site)
                      |
                      v
              titaniq-api (Render Web Service, Docker)
                      |
        +-------------+-------------+
        |             |             |
        v             v             v
  titaniq-postgres  titaniq-redis  titaniq-worker (Celery, Docker)
   (Render Postgres) (Render Redis)      |
                                          v
                                   titaniq-beat (Celery Beat, Docker)
                                          |
                            +-------------+-------------+
                            |             |             |
                            v             v             v
                      Sports APIs      Gemini      Flutterwave
```

Six services, matching the repository's real architecture — nothing collapsed, nothing invented:

| Service | Render type | Source |
|---|---|---|
| `titaniq-frontend` | Static Site | `frontend/` (Vite build) |
| `titaniq-api` | Web Service (Docker) | `backend/Dockerfile`, `uvicorn apps.api.main:app` |
| `titaniq-worker` | Background Worker (Docker) | `celery -A apps.worker.bootstrap worker` |
| `titaniq-beat` | Background Worker (Docker) | `celery -A apps.worker.bootstrap beat` |
| `titaniq-postgres` | Managed Postgres | new — see §5, critical caveat |
| `titaniq-redis` | Managed Redis (Key Value) | broker, cache, locks, rate limiting |

All defined in [`render.yaml`](../../render.yaml) at the repo root (a Render Blueprint — connect
the repo once in the Render dashboard and it provisions all six from this one file).

---

## 2. Real commands (verified against this repository, not assumed)

| Purpose | Command | Source |
|---|---|---|
| Backend install | `pip install .` (prod) / `pip install ".[dev]"` (CI) | `backend/pyproject.toml` |
| Backend start | `uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-4}` | `backend/Dockerfile` CMD |
| Migrations | `python -m alembic upgrade head` | run before `uvicorn` starts, see `render.yaml`'s `dockerCommand` |
| Celery worker | `celery -A apps.worker.bootstrap worker --loglevel=info` | `backend/apps/worker/bootstrap.py` |
| Celery Beat | `celery -A apps.worker.bootstrap beat --loglevel=info` | same module — **separate process**, never combined with the worker command |
| Frontend build | `npm ci && npm run build` (= `tsc -b && vite build`) | `frontend/package.json` |
| Frontend dev | `npm run dev` (Vite, port 5173) | — not used in production |
| Backend tests | `python -m pytest tests/unit -q` | 2,758 tests, ~19 min full run, all passing as of this doc |
| Frontend tests | `npm run test` (Vitest) | 89/90 passing — see §12 known issue |
| Python version | `>=3.12` | `backend/pyproject.toml`, Dockerfile uses `python:3.12-slim-bookworm` |
| Node version | not pinned in `package.json`; CI workflow uses Node 20 | `.github/workflows/ci.yml` |

None of these were guessed — each was read directly from the repository or its Dockerfile.

---

## 3. CRITICAL — the production database will start empty

**This is the single most important thing to understand before deploying.** `render.yaml`
provisions a brand-new, empty `titaniq-postgres` database. There is currently **no migration path
from the real data in `backend/dev.db` (SQLite)** — the synced fixtures, teams, competitions,
historical match data, and trained Champion models this session built and tested against — **into
that new Postgres instance**.

Deploying as-is means production launches with:
- Zero sports data (no fixtures, teams, competitions, players)
- Zero trained models (`NoChampionModelError` for every single market)
- A prediction engine that cannot generate anything until real provider syncs and model training
  run from scratch against production data — which takes real time and real provider quota, and
  for some markets requires a meaningful volume of completed matches before a model can even train

If that's not what you want (and given everything already working in `dev.db`, it almost
certainly isn't), a real data-migration pass — exporting `dev.db`'s tables and loading them into
Postgres, respecting the same schema (SQLAlchemy's dialect-generic column types already support
both) — needs to happen **before** go-live, as its own deliberate, reviewed step. This was not
attempted here; it needs your explicit sign-off given the scale and irreversibility of seeding a
production database.

---

## 4. Environment variables — real checklist

Corrected against what this repository *actually* reads (not a generic template — e.g. this app
has no `STRIPE_*` variables at all; billing is Flutterwave, credentialed through the admin
credential vault in the database, not env vars; Google OAuth needs no backend env var at all,
since Supabase holds that client ID/secret on its own side).

### Backend (`titaniq-api`, `titaniq-worker`, `titaniq-beat` — same set)

| Variable | Required | Source of value | Notes |
|---|---|---|---|
| `TITANIQ_DB_URL` | Yes | Render (`fromDatabase`) | Auto-wired by `render.yaml` |
| `TITANIQ_REDIS_URL` | Yes | Render (`fromService`) | Auto-wired by `render.yaml` |
| `TITANIQ_SUPABASE_PROJECT_URL` | Yes | Public, already in `render.yaml` | Not a secret — same value as frontend's `VITE_SUPABASE_URL` |
| `TITANIQ_ENCRYPTION_KEY` | Yes | **You generate, `sync: false`** | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — a fresh key, never reused from local dev |
| `TITANIQ_CORS_ORIGINS` | Yes (api only) | Set to the real frontend URL once known | Defaults to localhost only — **must** be updated or the frontend can't call the API |
| `TITANIQ_ENABLE_OFFLINE_AUTH` | No | `false` | Keep off in production — real auth is Supabase JWT only |
| `WEB_CONCURRENCY` | No | `2`–`4` per Render plan's CPU | uvicorn worker count |

### Frontend (`titaniq-frontend`)

| Variable | Required | Source of value | Notes |
|---|---|---|---|
| `VITE_API_BASE_URL` | Yes | The real `titaniq-api` URL | Fails the build loudly if unset in production (fixed this session — see `frontend/src/lib/env.ts`) |
| `VITE_SUPABASE_URL` | Yes | Public | Same as backend's |
| `VITE_SUPABASE_ANON_KEY` | Yes | Public | Supabase's anon/publishable key is meant to ship in a browser bundle — RLS enforces access server-side |

### What this app does NOT have (present in generic checklists, absent here — confirmed by reading the code, not assumed)

- `SECRET_KEY` / `JWT_SECRET` — auth is delegated entirely to Supabase; the backend verifies JWTs against Supabase's own rotating JWKS endpoint, no shared secret to configure
- `GOOGLE_CLIENT_ID` — configured only in the Supabase dashboard (Authentication → Providers → Google), never in this app's own environment
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` — this app uses **Flutterwave**, not Stripe. Flutterwave's client ID/secret live in the admin credential vault (database-backed, Fernet-encrypted with `TITANIQ_ENCRYPTION_KEY`), registered through the Ops Center UI post-deploy — not an env var at all
- `GEMINI_API_KEY` / provider keys (API-Football, football-data.org, etc.) — same pattern as Flutterwave: registered through the admin credential vault UI after the API is live, not env vars
- `SPORTS_PROVIDER_KEYS` — no such single variable; each provider's credential is entered individually via the vault

This is a deliberate architectural choice already in the codebase (`modules/admin` credential
vault), not a gap — provider/payment/AI credentials are operational data an admin manages at
runtime, not deploy-time configuration.

---

## 5. Database migrations

Current head: **`0045`** (single head, no branching — verified via `alembic heads`). 46 migration
files. A sample of the 5 most recent plus a full grep pass found every forward `upgrade()`
additive (`add_column`, `create_table`, `create_index`); `drop_table`/`drop_column` only appear
inside `downgrade()` in the sampled set. **No destructive forward migration was found** — nothing
here triggers this document's own stop condition. (Not an exhaustive line-by-line audit of all 46
files' `upgrade()` bodies — a full pre-flight read of every migration is still worth doing
immediately before the first real production migration run, since this is a one-shot,
high-consequence action against a real database.)

`render.yaml`'s `titaniq-api` service runs `python -m alembic upgrade head` before starting
`uvicorn`, every deploy — so migrations always apply before the app becomes reachable, matching
this document's required ordering.

## 6. Database backup

**Not required for the first deploy** — `titaniq-postgres` is a brand-new database with no
production data yet (see §3). There is nothing to back up on day one.

Once real data exists: Render's paid Postgres plans include automated daily backups with
point-in-time recovery, configured in the Render dashboard (Database → Backups) — this is
Render's own managed mechanism, not something this repository needs to implement. Retention and
restore procedure are Render's documented behavior for the plan tier chosen; verify the specific
plan's retention window in the Render dashboard once the database is provisioned, and run one real
test restore into a throwaway branch database before trusting it for an actual incident (Render
supports database branching for exactly this).

---

## 7. Redis

`titaniq-redis` (Render Key Value) serves every existing use in this codebase — no new caching
layer introduced: Celery broker/result backend, `RedisFeatureStore` (online feature cache),
`RedisDistributedLock` (sync-job mutual exclusion), and the rate limiter (`apps/api/rate_limit.py`,
`INCR`+`EXPIRE`). All read `TITANIQ_REDIS_URL` — one variable, one Redis instance, auto-wired by
`render.yaml`. `maxmemoryPolicy: allkeys-lru` is set explicitly (the codebase never configured an
eviction policy before — see the Production Readiness Audit's Redis finding).

---

## 8. Celery Worker & Beat

Deployed as two **separate** Render services (`titaniq-worker`, `titaniq-beat`), both Docker,
both built from the same `backend/Dockerfile` with a different `dockerCommand` overriding the
image's default `CMD`. Confirmed: nothing in this repository ever runs Beat inside the worker
process or the API process — the two `celery -A apps.worker.bootstrap ...` commands are
independent invocations of the same Celery app object, which is how this codebase already
structures it locally.

**Exactly one Beat instance**: Render Background Workers don't autoscale by default (unlike Web
Services), so a single `titaniq-beat` service with one instance is the correct, safe configuration
— do not scale this specific service beyond 1 instance, or the same scheduled task fires multiple
times per interval.

Real scheduled tasks (from `beat_schedule.py`, unchanged by this deployment): live fixtures every
30s, standings hourly, structured intelligence/news every 15 min, provider health every 5 min,
retraining/calibration checks every 6h/1h. Retraining itself is gated behind real preflight checks
(sample size, leakage, chronological holdout) inside the task, not merely timer-driven — confirmed
in the Production Readiness Audit.

---

## 9. Timezone

Confirmed UTC-consistent throughout the backend: every timestamp construction found in this
codebase's application/domain code uses `datetime.now(timezone.utc)`, not naive `datetime.now()`.
SQLite (local dev) drops timezone info on read-back — the codebase already has a documented,
repeated fix pattern for this (`_ensure_aware()` helpers in `sync_orchestrator.py`,
`windowed_feature_engineering_service.py`, etc., re-stamping a naive value as UTC on read). This
SQLite quirk does not apply to Postgres, which preserves `timestamptz` natively — one class of
bug this migration to Postgres removes, not introduces. No code change was needed here; this
section documents the existing, already-correct posture rather than a fix.

---

## 10. CORS

`backend/apps/api/main.py`'s CORS middleware already reads `TITANIQ_CORS_ORIGINS` from the
environment as a comma-separated allowlist — never a wildcard, confirmed in the Production
Readiness Audit. The only production action needed is setting that variable to the real
`titaniq-frontend` URL once it exists (placeholder value in `render.yaml` today —
`https://titaniq-frontend.onrender.com` — update if Render assigns a different subdomain, or once
a custom domain is attached).

---

## 11. Health checks

Two endpoints now exist (added this session, `backend/apps/api/main.py`):

- **`GET /api/v1/health`** — lightweight liveness only, always returns `{"status": "ok"}` if the
  process is up. This is what `render.yaml`'s `healthCheckPath` and the Dockerfile's `HEALTHCHECK`
  both point at — a Redis or Postgres blip must never make Render conclude the API process itself
  is dead and cycle it.
- **`GET /api/v1/health/ready`** — real dependency check (a live `SELECT 1` against the database, a
  live Redis `PING`), returns `503` if either is unreachable. No connection string, hostname, or
  exception detail is exposed — only `"healthy"`/`"unhealthy"` per dependency. Verified locally:
  correctly reports `database: healthy` against the real SQLite dev DB and `redis: unhealthy` when
  no local Redis is running, with the right 503 status.

---

## 12. Known issues going into deployment

- **`insights-page.test.tsx`**: one frontend test (`pins a team from search...`) fails —
  confirmed pre-existing (reproduces identically with every change from this session's work
  reverted), not a regression. Does not block deployment; worth its own investigation separately.
- **ML model artifact storage** (Production Readiness Audit §4): `LocalFilesystemArtifactStore`
  writes to a local `.model_artifacts/` directory. Render's Docker filesystem is not persistent
  across deploys or shared between the API/worker services — a model trained by `titaniq-worker`
  would not be visible to `titaniq-api` unless both happen to still be running the exact same
  container instance from before a redeploy. **This needs a real object-storage adapter
  (`ModelArtifactStorePort` already exists as the extension point) before models can survive a
  redeploy in production** — not addressed by this deployment pass.
- **CI** (`.github/workflows/ci.yml`, added this session): runs backend `pytest tests/unit` and
  frontend `npm run build` + `npm run test` on push/PR to `main`. Render's own GitHub integration
  deploys on push regardless of CI status — GitHub branch protection requiring this workflow to
  pass before merge is the actual enforcement point, not this file alone. Not yet configured
  (requires a repo settings change only you can make).

---

## 13. What has NOT been done (requires a live Render account)

Everything below requires actual Render credentials and a live deployment, neither of which exist
in this working environment:

- Provisioning any of the six services
- Running the first real migration against production Postgres
- Any live smoke test (frontend load, API health, auth flow, prediction generation, Celery task
  dispatch, Beat schedule firing) against a real deployed URL
- Attaching a custom domain / DNS / SSL verification
- Configuring Google OAuth's authorized redirect URI for the real production frontend domain
  (same class of fix as the `redirect_uri_mismatch` found and explained earlier this session for
  local dev — production needs its own, different authorized URI added in Google Cloud Console)
- Registering real provider/Gemini/Flutterwave credentials into the (currently empty, freshly
  provisioned) production credential vault

## 14. Rollback

- **Application (API/worker/beat)**: Render keeps prior deploys; roll back to the last known-good
  deploy from the Render dashboard's deploy history — a few clicks, no code change needed.
- **Frontend**: same — Render's static-site deploys are individually rollback-able.
- **Database migrations**: only as reversible as each migration's own `downgrade()` — the sampled
  recent migrations all had real, matching downgrades (additive-forward implies subtractive-
  backward here), but this was not verified for all 46 files. Do not assume every migration is
  safely reversible without checking that specific file first.
- **Model artifacts**: no rollback mechanism exists yet — this is the same gap noted in §12; the
  `ModelRegistryService.rollback()` application-layer method (real, reverts the Champion pointer
  to the previously-retired model) is unaffected, but restoring the actual artifact bytes for that
  prior Champion depends on whatever artifact storage gets built to replace the local-filesystem
  store.
- **Environment/secrets**: keep a secure, non-repository record of every `sync: false` value
  entered into Render (the encryption key especially — losing it makes every existing encrypted
  credential in the vault unrecoverable, not just newly-added ones).
