"""One-off: copy real data from local dev.db (SQLite) into a real Postgres database (Supabase).

Migrates only the "real, non-empty, migration-worthy" tables identified in this session's
production-readiness audit — not local dev/test identity data (users, sessions, tokens), which
has no place in a real deployment; real users register fresh via Supabase Auth there.

FK-safe insertion order is computed automatically from each table's real SQLAlchemy foreign keys
(restricted to edges between tables actually being migrated), not hand-ordered — hand-ordering
50 tables across 7 schemas is exactly the kind of thing that quietly gets one relationship wrong.

Every row's primary key is preserved verbatim (UUIDs pass through unchanged), so anything that
already references these ids (predictions -> prediction_markets, fixtures -> teams, etc.) stays
correctly linked with zero re-mapping.

Usage:
    TITANIQ_TARGET_DB_URL=postgresql://... python scripts/migrate_dev_db_to_postgres.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import JSON, Boolean, MetaData, create_engine, insert, select
from sqlalchemy.engine import Engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.admin.infrastructure.persistence.models import Base as AdminBase
from modules.features.infrastructure.persistence.models import Base as FeaturesBase
from modules.ingestion.infrastructure.persistence.models import Base as IngestionBase
from modules.intelligence.infrastructure.persistence.models import Base as IntelligenceBase
from modules.knowledge_graph.infrastructure.persistence.models import Base as KnowledgeGraphBase
from modules.predictions.infrastructure.persistence.models import Base as PredictionsBase
from modules.sports.infrastructure.persistence.models import Base as SportsBase

ALL_BASES = [SportsBase, AdminBase, FeaturesBase, IngestionBase, IntelligenceBase, KnowledgeGraphBase, PredictionsBase]

# "schema.table" -> real, non-empty, migration-worthy (per this session's data inventory).
# Deliberately excludes: identity/session/token tables (local dev accounts only — real users
# register fresh via Supabase Auth), and every table confirmed empty in dev.db (nothing to lose).
MIGRATE_TABLES = {
    "sports.sports", "sports.countries", "sports.venues", "sports.competitions", "sports.seasons",
    "sports.teams", "sports.players", "sports.coaching_staff", "sports.officials", "sports.fixtures",
    "sports.matches", "sports.team_statistics", "sports.standings", "sports.lineups", "sports.injuries",
    "sports.transfers", "sports.market_lines",
    "admin.providers", "admin.provider_credentials", "admin.provider_health_checks",
    "admin.provider_health_state", "admin.provider_incidents", "admin.provider_usage_records",
    "features.feature_definitions", "features.feature_values_offline",
    "ingestion.sync_checkpoints", "ingestion.sync_runs", "ingestion.provider_ref_index",
    "ingestion.data_quality_reports", "ingestion.timeline_events",
    "ingestion.competition_fixture_source_preferences",
    "intelligence.news_sources", "intelligence.news_articles", "intelligence.news_events",
    "intelligence.impact_scores", "intelligence.intelligence_sync_checkpoints",
    "intelligence.intelligence_sync_runs", "intelligence.source_reliability_scores",
    "knowledge_graph.kg_nodes", "knowledge_graph.kg_edges",
    "predictions.prediction_markets", "predictions.feature_market_mappings", "predictions.models",
    "predictions.predictions", "predictions.prediction_outcomes", "predictions.prediction_audits",
    "predictions.prediction_context_reviews", "predictions.prediction_football_explanations",
    "predictions.datasets", "predictions.experiments", "predictions.calibration_reports",
}


def _collect_target_tables() -> dict[str, "MetaDataTable"]:  # noqa: F821 - typing convenience only
    tables = {}
    for base in ALL_BASES:
        for key, table in base.metadata.tables.items():
            if key in MIGRATE_TABLES:
                tables[key] = table
    missing = MIGRATE_TABLES - set(tables.keys())
    if missing:
        raise RuntimeError(f"MIGRATE_TABLES references tables not found in any module's ORM metadata: {missing}")
    return tables


def _topological_order(tables: dict) -> list[str]:
    """Kahn's algorithm — an edge child->parent exists whenever child has an FK column pointing
    at parent's primary key, restricted to parent/child both being in `tables` (an FK to a table
    we're deliberately not migrating, e.g. identity.users, is not a real ordering constraint here
    since that data isn't being inserted at all)."""
    deps: dict[str, set[str]] = defaultdict(set)
    for key, table in tables.items():
        for fk in table.foreign_keys:
            parent_key = f"{fk.column.table.schema}.{fk.column.table.name}"
            if parent_key in tables and parent_key != key:
                deps[key].add(parent_key)

    ordered: list[str] = []
    remaining = set(tables.keys())
    while remaining:
        ready = sorted(k for k in remaining if deps[k] <= set(ordered))
        if not ready:
            raise RuntimeError(f"Circular or unresolvable FK dependency among: {remaining}")
        ordered.extend(ready)
        remaining -= set(ready)
    return ordered


def _load_sqlite_rows(sqlite_path: Path, table_name: str) -> list[dict]:
    con = sqlite3.connect(str(sqlite_path))
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(f'SELECT * FROM "{table_name}"')
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows


def _coerce_row(row: dict, table) -> dict:
    """SQLite has no native JSON/boolean types — sqlite3 hands back raw TEXT for JSON columns
    and 0/1 integers for booleans. SQLAlchemy's Postgres JSON/Boolean column types need real
    Python objects (dict/list, bool) to bind correctly, not their SQLite wire representation."""
    coerced = dict(row)
    for col in table.columns:
        name = col.name
        if name not in coerced or coerced[name] is None:
            continue
        if isinstance(col.type, JSON) and isinstance(coerced[name], str):
            coerced[name] = json.loads(coerced[name])
        elif isinstance(col.type, Boolean) and isinstance(coerced[name], int):
            coerced[name] = bool(coerced[name])
    return coerced


def _fk_edges_within(table, tables: dict) -> list[tuple[str, str, str]]:
    """(local_column_name, parent_table_key, parent_pk_column_name) for every FK on `table` whose
    target is itself one of the tables being migrated (an FK to e.g. identity.users, which we're
    deliberately not migrating, isn't something we can or need to validate here)."""
    edges = []
    for fk in table.foreign_keys:
        parent_key = f"{fk.column.table.schema}.{fk.column.table.name}"
        if parent_key in tables:
            edges.append((fk.parent.name, parent_key, fk.column.name))
    return edges


def _run(sqlite_path: Path, tables: dict, order: list[str], conn, *, dry_run: bool) -> list[tuple[str, int, int, int]]:
    # Running set of each already-migrated table's real primary-key values, keyed by "schema.table"
    # -> {pk_value, ...}. Used to drop rows whose FK points at something that was never actually
    # migrated (or never existed) — dev.db itself has a handful of these (e.g. 8
    # admin.provider_credentials rows referencing a provider_id no current provider has), and
    # inserting them as-is would just violate the target's real FK constraints.
    migrated_pks: dict[str, set] = {}
    summary = []

    for key in order:
        table = tables[key]
        source_rows = _load_sqlite_rows(sqlite_path, table.name)
        if not source_rows:
            summary.append((key, 0, 0, 0))
            migrated_pks[key] = set()
            continue

        coerced = [_coerce_row(r, table) for r in source_rows]
        valid_cols = {c.name for c in table.columns}
        payload = [{k: v for k, v in r.items() if k in valid_cols} for r in coerced]

        edges = _fk_edges_within(table, tables)
        dropped = 0
        if edges:
            kept = []
            for row in payload:
                ok = True
                for local_col, parent_key, _parent_pk_col in edges:
                    value = row.get(local_col)
                    if value is None:  # nullable FK, not set — nothing to validate
                        continue
                    if value not in migrated_pks.get(parent_key, set()):
                        ok = False
                        print(f"  DROPPING {key} row (id={row.get('id', value)}): "
                              f"{local_col}={value} not found in migrated {parent_key}")
                        break
                if ok:
                    kept.append(row)
                else:
                    dropped += 1
            payload = kept

        if conn is not None and payload:
            conn.execute(insert(table), payload)

        pk_cols = list(table.primary_key.columns.keys())
        if len(pk_cols) == 1:
            migrated_pks[key] = {row[pk_cols[0]] for row in payload}
        else:
            migrated_pks[key] = set()  # composite PK — no table in this migrate set is referenced by one

        summary.append((key, len(source_rows), len(payload), dropped))
        drop_note = f" ({dropped} dropped, dangling FK)" if dropped else ""
        print(f"{'[DRY RUN] would insert' if dry_run else 'inserted'} {len(payload)} rows into {key}{drop_note}")
    return summary


def migrate(sqlite_path: Path, target_engine: Engine | None, *, dry_run: bool) -> None:
    tables = _collect_target_tables()
    order = _topological_order(tables)

    print(f"Migration order ({len(order)} tables):")
    for key in order:
        print(f"  {key}")
    print()

    if dry_run:
        summary = _run(sqlite_path, tables, order, None, dry_run=True)
    else:
        with target_engine.begin() as conn:
            summary = _run(sqlite_path, tables, order, conn, dry_run=False)

    print()
    print("Summary (table, source_rows, inserted, dropped_dangling_fk):")
    total_dropped = 0
    for key, src, ins, dropped in summary:
        total_dropped += dropped
        expected = src - dropped
        marker = "" if ins == expected else "  <-- UNEXPECTED MISMATCH"
        print(f"  {key}: {src} -> {ins} (dropped {dropped}){marker}")
    if total_dropped:
        print(f"\n{total_dropped} total rows dropped for referencing something never migrated — see DROPPING lines above for exactly which.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted without writing")
    parser.add_argument("--sqlite-path", default=str(Path(__file__).resolve().parent.parent / "dev.db"))
    args = parser.parse_args()

    import os

    if args.dry_run:
        migrate(Path(args.sqlite_path), None, dry_run=True)
    else:
        target_url = os.environ.get("TITANIQ_TARGET_DB_URL")
        if not target_url:
            raise SystemExit("Set TITANIQ_TARGET_DB_URL to the target Postgres connection string (sync driver, e.g. postgresql://...)")
        engine = create_engine(target_url)
        migrate(Path(args.sqlite_path), engine, dry_run=False)
