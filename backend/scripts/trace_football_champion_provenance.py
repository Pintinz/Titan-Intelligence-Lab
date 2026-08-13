"""Milestone 4 item 5: traces every football CHAMPION model's training provenance and reports
whether it should be `PROVENANCE_VERIFIED` or stay `PROVENANCE_UNVERIFIED`.

This is a READ-ONLY report, not a backfill — it never writes `provenance_status` itself. Per the
master prompt's "never fabricate a verified state" rule, promoting a model to `PROVENANCE_VERIFIED`
requires a human to review this report's findings and confirm the training lineage is genuinely
reconstructable and leakage-free, not just that a `dataset_version`/`trained_at` value exists.

A model is classified `TRAINED` (has `artifact_ref` — see
`ModelDefinition.is_genuinely_trained()`) or `HEURISTIC_PLACEHOLDER` (registered only to unblock
`PredictionContextBuilder`, never actually fit — see market_router.py's `_training_status`).
`TRAINED` models are further flagged `provenance_traceable` only when both `training_dataset_ref`
and `training_run_ref` are populated, i.e. the exact dataset build and training run that produced
them can be independently pulled up — as of this migration's writing, no current Champion carries
either field (they predate `AutomaticModelSelectionService`'s dataset/training-run-ref population),
so every one of them is expected to report `provenance_traceable=False` today. This is a known,
documented gap, not a bug this script fixes.

Usage: python scripts/trace_football_champion_provenance.py [--db-path dev.db]
"""

from __future__ import annotations

import argparse
import sqlite3


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default="dev.db")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT m.market_key, mo.algorithm, mo.artifact_ref IS NOT NULL AS has_artifact,
                   mo.dataset_version, mo.training_dataset_ref, mo.training_run_ref,
                   mo.trained_at, mo.promoted_at, mo.provenance_status
            FROM models mo JOIN prediction_markets m ON m.id = mo.market_id
            WHERE mo.status = 'champion' AND m.sport_code = 'football'
            ORDER BY m.market_key
            """
        )
        rows = cur.fetchall()

        trained, heuristic = 0, 0
        for row in rows:
            is_trained = bool(row["has_artifact"])
            provenance_traceable = is_trained and bool(row["training_dataset_ref"]) and bool(row["training_run_ref"])
            if is_trained:
                trained += 1
            else:
                heuristic += 1
            print(
                f"{row['market_key']:55s} "
                f"{'TRAINED' if is_trained else 'HEURISTIC_PLACEHOLDER':22s} "
                f"algorithm={row['algorithm']:22s} "
                f"dataset_version={row['dataset_version']} "
                f"provenance_traceable={provenance_traceable} "
                f"provenance_status={row['provenance_status']}"
            )
            if row["provenance_status"] == "PROVENANCE_VERIFIED" and not provenance_traceable:
                print(
                    f"  WARNING: {row['market_key']} is marked PROVENANCE_VERIFIED but its training "
                    f"dataset/run cannot be independently traced — this claim should be re-reviewed."
                )

        print(f"\n{len(rows)} football Champions: {trained} genuinely trained, {heuristic} heuristic placeholder.")
        print(
            "No row's provenance_status was written by this script — it is read-only. Promoting any "
            "model to PROVENANCE_VERIFIED is a separate, deliberate, human-reviewed action."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
