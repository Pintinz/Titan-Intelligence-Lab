# TitanIQ — Deployment

Status: Development/staging deployment against the live `titaniq` Supabase project as of
Milestone 6. Production launch checklist (backups, DR drills, formal security review) remains
gated at Milestone 20 per [security.md](security.md) §8. This document covers what's needed to
actually run the backend against the real project today.

## 1. Required environment variables

| Var | Required for | Notes |
|---|---|---|
| `TITANIQ_DB_URL` | Running the FastAPI app for real | `postgresql+asyncpg://postgres:<password>@db.irhnoilyaqgewfidhunx.supabase.co:5432/postgres` — get `<password>` from Supabase Dashboard → Settings → Database. For fast local tests use `sqlite+aiosqlite://` instead (existing pattern since Milestone 2). |
| `TITANIQ_REDIS_URL` | Feature store, ingestion cache/locks | Since Milestone 4 |
| `TITANIQ_ENCRYPTION_KEY` | Provider credential + webhook signing-secret encryption | `Fernet.generate_key()`, since Milestone 3 |
| `TITANIQ_SUPABASE_PROJECT_URL` | JWT validation (`SupabaseJWKSValidator`) | `https://irhnoilyaqgewfidhunx.supabase.co` |
| `TITANIQ_SUPABASE_JWKS_CACHE_SECONDS` | Optional, JWKS cache TTL | Defaults to 3600 |

None of these are fabricated by the assistant — every value with a real secret is supplied by
the user; see [supabase.md](supabase.md) §9.

## 2. Running database migrations against live Supabase

The assistant cannot open a direct Alembic connection to the live database (no DB password) —
migrations 0001-0014 were applied via offline-SQL-generation + the Supabase MCP's `execute_sql`
tool instead (docs/decisions.md ADR-024, full procedure in [supabase.md](supabase.md) §3). If
you have `TITANIQ_DB_URL` with the real password, the normal path also works directly:

```bash
TITANIQ_DB_URL="postgresql+asyncpg://postgres:<password>@db.irhnoilyaqgewfidhunx.supabase.co:5432/postgres" \
  alembic upgrade head
```

## 3. Running the test suites

```bash
pytest tests/unit          # fast, offline, SQLite/fakeredis/MockJWTValidator — always runs
pytest tests/integration   # live Supabase — skips cleanly (not failure) without credentials
```

To actually run the integration tier, set (see [supabase.md](supabase.md) §9 for what each is):

```bash
export TITANIQ_INTEGRATION_DB_URL="postgresql+asyncpg://postgres:<password>@db.irhnoilyaqgewfidhunx.supabase.co:5432/postgres"
export TITANIQ_SUPABASE_PROJECT_URL="https://irhnoilyaqgewfidhunx.supabase.co"
export TITANIQ_SUPABASE_ANON_KEY="<publishable key from Settings -> API>"
# For tests/integration/test_authorization.py specifically, TITANIQ_DB_URL must ALSO point at
# the live instance (same value as TITANIQ_INTEGRATION_DB_URL) — that file drives the real
# apps.api.main.app wiring end-to-end, not a dependency-overridden test client.
export TITANIQ_DB_URL="$TITANIQ_INTEGRATION_DB_URL"
pytest tests/integration
```

Every test in this tier creates its own fixture data inside a transaction that is rolled back
(RLS/database tests) or against dedicated per-test-run email addresses (`unique_test_email`
fixture, Auth/Storage tests) — nothing persists in the live project from a normal test run.

## 4. Auth Provider Setup (manual — no MCP tool covers this)

No Supabase MCP tool configures Auth provider settings (OAuth client id/secret, email
templates, SMTP) — that lives only in the Supabase Dashboard or the separate Management API,
neither of which is exposed to the assistant's tools. Email/Password, Magic Links, and
mandatory email verification are already on by default for this hosted project — no action
needed there.

**Google** (code-side already complete — [authentication.md](authentication.md) §6):
1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials →
   Create OAuth client ID (Web application).
2. Authorized redirect URI: `https://irhnoilyaqgewfidhunx.supabase.co/auth/v1/callback`.
3. Supabase Dashboard → Authentication → Providers → Google → paste Client ID + Client Secret →
   Enable.

**GitHub** (code-side already complete):
1. GitHub → Settings → Developer settings → OAuth Apps → New OAuth App.
2. Authorization callback URL: `https://irhnoilyaqgewfidhunx.supabase.co/auth/v1/callback`.
3. Supabase Dashboard → Authentication → Providers → GitHub → paste Client ID + Client Secret →
   Enable.

**Apple** (interface-ready, not yet configured):
1. Apple Developer account required — Certificates, Identifiers & Profiles → create a Services
   ID + Sign in with Apple key.
2. Supabase Dashboard → Authentication → Providers → Apple → paste the Services ID, Team ID,
   Key ID, and private key.

**Microsoft** (interface-ready, not yet configured — Supabase calls this provider `azure`):
1. [Azure Portal](https://portal.azure.com/) → App registrations → New registration.
2. Redirect URI: `https://irhnoilyaqgewfidhunx.supabase.co/auth/v1/callback`.
3. Supabase Dashboard → Authentication → Providers → Azure → paste Application (client) ID,
   Client Secret, and Tenant ID (or `common` for multi-tenant) → Enable.

No code changes are needed once any of these are enabled in the dashboard — `apps.api.auth_deps`
already maps every one of these provider identifiers to `IdentityProvider` and auto-links a
`FederatedIdentity` on first login.

## 5. Production readiness (not yet done, Milestone 20 gate)

Automated Postgres backups, defined RPO/RTO targets, restore drills, formal security review —
see [security.md](security.md) §5, §8. Not started.
