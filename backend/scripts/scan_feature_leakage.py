"""Training-data leakage scanner (forensic audit §9, Critical Fix #1 follow-up).

Every point-in-time bug this codebase has actually had shares one observable signature: a
fixture-scoped feature row in the offline feature store (`feature_values_offline`, entity_type
= "fixture") whose `as_of` timestamp is *later* than the fixture's own `scheduled_at`. A feature
meant to represent "this team's rolling form/expected goals as of this fixture's kickoff" can
never legitimately be true if it was computed after that kickoff — any row like that proves either
a leaky batch cutoff (the exact bug fixed in the six `backfill_*_training_data.py` scripts and the
three `FixtureExpectedGoalsCalculator` call sites this session) or a live re-sync recomputing an
already-completed historical fixture without a fixture-specific cutoff.

This does not (and cannot, from this table alone) prove a specific `Prediction.feature_snapshot`
was built from a contaminated read — `Prediction.feature_snapshot` stores only the resolved value,
never which `as_of` it was read at (a separate, real audit finding — see the forensic report).
What it proves is narrower but load-bearing: whether contaminated *rows* exist in the feature store
at all, which is a necessary precondition for any prediction built from them to be contaminated.

Never silently logs a violation and continues — exits non-zero and prints DATASET_REJECTED when
any violation is found, so this can gate a CI/backfill pipeline rather than merely inform one.

Usage:
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/scan_feature_leakage.py
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/scan_feature_leakage.py --json report.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine

DATASET_VERSION = "feature_values_offline (live table, not a frozen dataset snapshot)"


@dataclass
class LeakageViolation:
    fixture_id: str
    feature_key: str
    scheduled_at: str
    offending_as_of: str
    lead_time_seconds: float
    source: str = "feature_values_offline"
    severity: str = "CRITICAL"


def _parse_dt(raw) -> datetime:
    return datetime.fromisoformat(raw) if isinstance(raw, str) else raw


def _normalize_id(raw: str) -> str:
    """`fixtures.id` and `feature_values_offline.entity_id` have been written under both a dashed
    and an undashed hex form at different points in this repo's history (a real, separately-fixed
    bug — see `seed_football_markets.py`'s own docstring). Comparing on a SQL join condition
    wrapped in `REPLACE()` on both sides defeats any index and is O(rows_a * rows_b) on SQLite —
    with ~125k feature rows and ~8k fixtures that's untenable. Normalizing once in Python and
    matching via a dict is the same correctness with no join at all."""
    return raw.replace("-", "")


async def scan(session) -> list[LeakageViolation]:
    """Every `feature_values_offline` row keyed to a fixture, compared against that fixture's own
    `scheduled_at`, flagging rows where the feature was computed strictly after kickoff. Two plain
    SELECTs plus an in-memory dict lookup — see `_normalize_id` for why this avoids a SQL join."""
    fixture_rows = (await session.execute(text("SELECT id, scheduled_at FROM fixtures"))).all()
    kickoff_by_id = {_normalize_id(fixture_id): _parse_dt(scheduled_at) for fixture_id, scheduled_at in fixture_rows}

    feature_rows = (
        await session.execute(
            text(
                "SELECT entity_id, feature_key, as_of FROM feature_values_offline WHERE entity_type = 'fixture'"
            )
        )
    ).all()

    violations: list[LeakageViolation] = []
    for entity_id, feature_key, as_of_raw in feature_rows:
        scheduled_at = kickoff_by_id.get(_normalize_id(entity_id))
        if scheduled_at is None:
            continue  # orphaned feature row (fixture deleted/merged away) — not a leakage signal
        as_of = _parse_dt(as_of_raw)
        if as_of <= scheduled_at:
            continue
        violations.append(
            LeakageViolation(
                fixture_id=entity_id,
                feature_key=feature_key,
                scheduled_at=scheduled_at.isoformat(),
                offending_as_of=as_of.isoformat(),
                lead_time_seconds=(as_of - scheduled_at).total_seconds(),
            )
        )
    violations.sort(key=lambda v: v.scheduled_at)
    return violations


def _print_report(violations: list[LeakageViolation]) -> None:
    if not violations:
        print("LEAKAGE SCAN: PASS — no feature_values_offline row is stamped after its own fixture's kickoff.")
        return

    by_feature: dict[str, int] = {}
    fixtures: set[str] = set()
    for v in violations:
        by_feature[v.feature_key] = by_feature.get(v.feature_key, 0) + 1
        fixtures.add(v.fixture_id)

    print(f"LEAKAGE SCAN: DATASET_REJECTED — {len(violations)} violation(s) across {len(fixtures)} fixture(s)")
    print(f"dataset_version: {DATASET_VERSION}\n")
    print("Affected features:")
    for feature_key, count in sorted(by_feature.items(), key=lambda kv: -kv[1]):
        print(f"  {feature_key}: {count} row(s)")
    print("\nWorst offenders (largest post-kickoff lead time):")
    for v in sorted(violations, key=lambda v: -v.lead_time_seconds)[:15]:
        days = v.lead_time_seconds / 86400
        print(
            f"  fixture={v.fixture_id} feature={v.feature_key} "
            f"kickoff={v.scheduled_at} as_of={v.offending_as_of} (+{days:.0f}d) severity={v.severity}"
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", metavar="PATH", help="write the full violation report to this path as JSON")
    args = parser.parse_args()

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        violations = await scan(session)

    _print_report(violations)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "dataset_version": DATASET_VERSION,
                    "violation_count": len(violations),
                    "affected_fixtures": len({v.fixture_id for v in violations}),
                    "violations": [asdict(v) for v in violations],
                },
                f,
                indent=2,
            )
        print(f"\nFull report written to {args.json}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
