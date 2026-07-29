# TitanIQ — Supabase

Status: Live production development environment as of Milestone 6, replacing the "no live
Supabase project" assumption used during Milestones 2-5. Supabase remains infrastructure only
(docs/architecture.md's constitution) — FastAPI is responsible for all business logic; nothing
here is authorization/business logic, only "what infrastructure is configured and how."

## 1. Project identity

- **Project**: `titaniq`
- **Project ref**: `irhnoilyaqgewfidhunx`
- **Organization**: Autotechub (`scikxixjqvnwxasrhxwl`)
- **Region**: `eu-north-1`
- **Postgres**: 17.6.1.147 (engine 17, GA release channel)
- **Project URL**: `https://irhnoilyaqgewfidhunx.supabase.co`
- **Database host**: `db.irhnoilyaqgewfidhunx.supabase.co`

## 2. Schemas

App-owned (Alembic-managed, one linear migration history — `sports.alembic_version` is the
single source of truth, currently at `0014`):

| Schema | Owning milestone | Tables |
|---|---|---|
| `sports` | M2, M5 | 21 |
| `admin` | M3 | 7 |
| `features` | M4 | 9 |
| `ingestion` | M5 | 5 |
| `knowledge_graph` | M5 | 2 |
| `identity` | M6 | 8 |
| `tenancy` | M6 | 4 |
| `billing` | M6 | 4 |
| `webhooks` | M6 | 2 |

Supabase-managed infrastructure schemas (never touched by our migrations): `auth`, `storage`,
`realtime`, `vault`, `graphql`, `graphql_public`, `extensions`, `pgbouncer`, plus Postgres
system schemas.

## 3. How migrations are applied

The assistant does not have and must never fabricate the database password — real credentials
are supplied by the user via `TITANIQ_DB_URL`, never invented (same rule as every other secret
in this codebase). Migrations 0001-0014 were verified and applied against the live project
using a password-independent path (docs/decisions.md ADR-024):

1. Generate offline SQL: `TITANIQ_DB_URL="postgresql+asyncpg://user:pass@localhost/db" alembic
   upgrade <from>:<to> --sql` — the URL only needs a valid *dialect*, not real credentials,
   since `--sql` never opens a connection.
2. Strip the `INFO [alembic.runtime.migration]` log lines Alembic interleaves into that output
   (they are not valid SQL) — `grep -v '^INFO'` is sufficient for single-line log entries; watch
   for multi-line wrapped log messages, which leave dangling continuation-line fragments that
   also need removing.
3. Apply the cleaned SQL via the Supabase MCP server's `execute_sql` tool, which authenticates
   independently of the database password.
4. Verify via `list_tables` / a direct `SELECT version_num FROM sports.alembic_version` query.

`apply_migration` (a different MCP tool) is deliberately not used — it records changes in
Supabase's own `supabase_migrations` schema, a second ledger that would run in parallel with
`sports.alembic_version`. `execute_sql` has no side ledger, keeping Alembic the single source of
truth.

## 4. Extensions

Installed: `plpgsql`, `uuid-ossp`, `pgcrypto`, `pg_stat_statements`, `supabase_vault`. Available
but not installed: `pgjwt`, `pgsodium`, `pgaudit`, `pg_cron`, `vector`, `postgis`, `pg_net`,
`wrappers`, and others — evaluate if a future milestone needs them (e.g. `pg_cron` for
scheduled cleanup of `temporary-files`, `vector` for embeddings-based features).

## 5. Row Level Security

Full reference: [rls.md](rls.md). Summary: all 62 app tables have RLS enabled; identity/
tenancy/billing/webhooks carry real ownership + RBAC-ladder policies; M2-M5 backend/catalog
tables are analyst+ read-only; security-internal tables (audit log, account lock state) have no
self-access policy at all.

## 6. Storage

7 buckets (migration 0013) — full policy reference in [rls.md](rls.md) §7:

| Bucket | Public | Size limit | Notes |
|---|---|---|---|
| `avatars` | Yes | 5 MB | Owner-writable, moderator+ can delete (moderation) |
| `team-logos` | Yes | 5 MB | administrator+ writable only |
| `competition-logos` | Yes | 5 MB | administrator+ writable only |
| `ai-reports` | No | 20 MB | Owner-only, administrator+ SELECT (support) |
| `generated-charts` | No | 20 MB | Owner-only, administrator+ SELECT |
| `uploads` | No | 25 MB | Owner-only, administrator+ SELECT |
| `temporary-files` | No | 50 MB | Owner-only scratch space; no automatic expiry job yet — a candidate for `pg_cron` in a future milestone |

## 7. Realtime

8 of 62 tables enabled (migration 0014), each mapped to a named use case — see
docs/decisions.md ADR-028 and [rls.md](rls.md) §8. Deliberately not "every table."

## 8. Auth

Email/Password, Magic Links, Email OTP, and mandatory email verification are on by default for
every hosted Supabase project — confirmed via Supabase's own docs, no dashboard action taken or
needed. OAuth provider dashboard configuration (Google/GitHub live-ready code-side, Apple/
Microsoft interface-ready) requires manual steps outside any tool available to the assistant —
see [deployment.md](deployment.md) §Auth Provider Setup, and [authentication.md](authentication.md)
for the code-side design.

## 9. Secrets this project needs, and where they come from

| Env var | Purpose | Source |
|---|---|---|
| `TITANIQ_DB_URL` | Real app runtime DB connection | Supabase Dashboard → Settings → Database (user-supplied) |
| `TITANIQ_SUPABASE_PROJECT_URL` | JWKS validation, JWT issuer check | `https://irhnoilyaqgewfidhunx.supabase.co` (not secret) |
| `TITANIQ_SUPABASE_ANON_KEY` | Client-side/integration-test API calls | Supabase Dashboard → Settings → API (publishable, not secret, but still env-sourced for portability) |
| `TITANIQ_INTEGRATION_DB_URL` | Live-database integration test tier only | Same as `TITANIQ_DB_URL`, kept as a separate var so it can never collide with the fast suite's SQLite config |

None of these are ever fabricated by the assistant — same rule as `TITANIQ_REDIS_URL`/
`TITANIQ_ENCRYPTION_KEY` established since Milestone 3.
