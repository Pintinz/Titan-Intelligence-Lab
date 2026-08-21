"""Predictive Signal Recovery charter, Phase 2: read-only feature-coverage diagnostic across every
registered market, grouped by sport and charter feature family. Never trains, never writes to the
database — reuses `PredictiveSignalAuditService.audit_all()` (Phase 1) entirely for its facts,
classifying each real `required_feature_keys`/`optional_feature_keys` entry via
`feature_family_taxonomy.classify_feature_key()`.

Verdict per (sport, family):
- WIRED_AND_POPULATED: at least one real feature_key matched this family, and its average
  missing_rate (from real, already-persisted Dataset.statistics, where available) is < 50%.
- WIRED_BUT_UNPOPULATED: at least one real feature_key matched this family, but its average
  missing_rate is >= 50% (or no dataset exists yet to measure it) — the exact pattern already
  found for football's lineup_continuity/transfer_activity/news_intelligence on the goals markets.
- DECLARED_BUT_NEVER_WRITTEN: the family's feature_key was required somewhere, but the sport has
  no real writer for it (currently only relevant to "odds" for non-football sports).
- NOT_FOUND_IN_REGISTERED_FEATURES: no real feature_key for this family was required/optional on
  any of this sport's markets — an honest "we saw nothing," not a claim that no calculator exists
  anywhere in the codebase (that stronger claim is reserved for
  `NO_CALCULATOR_CONFIRMED_FAMILIES`, reported separately).

The one filesystem write in the whole script is the markdown report file itself.

Usage:
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_feature_coverage_diagnostic.py
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_feature_coverage_diagnostic.py --output docs/feature_coverage_report.md
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_predictive_signal_audit_service, get_engine
from modules.predictions.application.feature_family_taxonomy import (
    NO_CALCULATOR_CONFIRMED_FAMILIES,
    SPORTS_WITH_REAL_ODDS_WRITER,
    classify_feature_key,
)
from modules.predictions.domain.market_audit import MarketAuditRecord

_UNPOPULATED_THRESHOLD = 0.5


def _family_stats(records: tuple[MarketAuditRecord, ...]) -> dict[str, dict[str, dict]]:
    """sport_code -> family -> {"markets": set[market_key], "missing_rates": list[float]}.

    A feature_key absent from `record.missing_rate` on a market that DOES have a persisted
    dataset means the feature never appeared in a single sample — 100% missing, matching
    `TrainingPreflightService._required_feature_coverage_acceptable()`'s own convention
    (`missing_rate.get(key, 1.0)`), not "no data to judge by." Only a market with no persisted
    dataset at all contributes no missing_rate observation for its required/optional features.
    """
    by_sport: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"markets": set(), "missing_rates": []}))
    for record in records:
        all_keys = set(record.required_feature_keys) | set(record.optional_feature_keys)
        for key in all_keys:
            family = classify_feature_key(key)
            if family is None:
                continue
            entry = by_sport[record.sport_code][family]
            entry["markets"].add(record.market_key)
            if record.has_persisted_dataset:
                entry["missing_rates"].append(record.missing_rate.get(key, 1.0))
    return by_sport


def _verdict(sport_code: str, family: str, entry: dict) -> str:
    if sport_code == "table_tennis":
        return "SPORT_UNSUPPORTED"
    if family == "odds" and sport_code not in SPORTS_WITH_REAL_ODDS_WRITER:
        return "DECLARED_BUT_NEVER_WRITTEN"
    rates = entry["missing_rates"]
    if not rates:
        return "WIRED_BUT_UNPOPULATED"
    avg_missing = sum(rates) / len(rates)
    return "WIRED_AND_POPULATED" if avg_missing < _UNPOPULATED_THRESHOLD else "WIRED_BUT_UNPOPULATED"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default="docs/feature_coverage_report.md", help="markdown report path")
    args = parser.parse_args()

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        service = build_predictive_signal_audit_service(session)
        records = await service.audit_all(now, include_preflight=False)

    by_sport = _family_stats(records)
    sports = sorted(by_sport.keys())

    lines = [
        "# TitanIQ Predictive Signal Recovery — Feature Coverage Diagnostic (Phase 2)",
        "",
        f"Generated {now.isoformat()}. {len(records)} markets audited across {len(sports)} sports.",
        "",
        "Families confirmed (via source-code review, not DB data) to have **zero** feature-",
        f"producing calculator anywhere in the codebase: {', '.join(NO_CALCULATOR_CONFIRMED_FAMILIES)}.",
        "",
    ]

    for sport_code in sports:
        lines.append(f"## {sport_code}")
        lines.append("")
        lines.append("| Family | Markets requiring it | Avg missing_rate | Verdict |")
        lines.append("|---|---|---|---|")
        families = sorted(by_sport[sport_code].keys())
        if not families:
            lines.append("| *(none found)* | - | - | NOT_FOUND_IN_REGISTERED_FEATURES |")
        for family in families:
            entry = by_sport[sport_code][family]
            rates = entry["missing_rates"]
            avg_missing = f"{sum(rates) / len(rates):.1%}" if rates else "n/a (no dataset yet)"
            verdict = _verdict(sport_code, family, entry)
            lines.append(f"| {family} | {len(entry['markets'])} | {avg_missing} | {verdict} |")
        for family in NO_CALCULATOR_CONFIRMED_FAMILIES:
            lines.append(f"| {family} | 0 | n/a | NO_CALCULATOR |")
        lines.append("")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"{len(records)} markets audited across {len(sports)} sports.")
    for sport_code in sports:
        families = by_sport[sport_code]
        wired = sum(1 for f in families if _verdict(sport_code, f, families[f]) == "WIRED_AND_POPULATED")
        print(f"  {sport_code}: {len(families)} families found, {wired} WIRED_AND_POPULATED")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
