"""One-off backfill: normalizes `provider_ref_index.entity_id` to the canonical hyphenated
`str(uuid.UUID(...))` form (Milestone 4, provider-reference join-format hardening — see
`modules/ingestion/infrastructure/persistence/mappers.py::_canonical_entity_id` for the full
finding, including why hex was tried first and reverted).

Every write to this column now passes through `_canonical_entity_id` at the mapper layer, so new
rows are already canonical. This script only touches rows written before that mapper fix landed.
Non-UUID values (none expected in this column, but tolerated defensively) are left untouched
rather than raised on, matching the mapper's own fallback behavior.

Run once against dev.db; safe to re-run (idempotent — rows already canonical are no-ops).

Usage: python scripts/normalize_provider_ref_index_entity_id.py [--db-path dev.db]
"""

from __future__ import annotations

import argparse
import sqlite3
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="dev.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT provider, external_id, entity_kind, entity_id FROM provider_ref_index")
        rows = cur.fetchall()

        updated = 0
        for provider, external_id, entity_kind, entity_id in rows:
            try:
                canonical = str(uuid.UUID(entity_id))
            except (ValueError, AttributeError, TypeError):
                continue
            if canonical != entity_id:
                print(f"  {provider}/{entity_kind}/{external_id}: {entity_id!r} -> {canonical!r}")
                cur.execute(
                    "UPDATE provider_ref_index SET entity_id = ? "
                    "WHERE provider = ? AND external_id = ? AND entity_kind = ?",
                    (canonical, provider, external_id, entity_kind),
                )
                updated += 1

        conn.commit()
        if updated:
            print(f"Normalized entity_id for {updated} provider_ref_index row(s).")
        else:
            print("No provider_ref_index rows needed normalization.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
