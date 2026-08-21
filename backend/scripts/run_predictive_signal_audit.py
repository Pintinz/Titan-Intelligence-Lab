"""Predictive Signal Recovery charter, Phase 1: read-only market matrix across every registered
market. Never trains, never writes to the database — reuses `PredictiveSignalAuditService`, which
itself only reads existing repositories plus (when preflight is included) the same read-only
`TrainingPreflightService.check()` gate `run_training_preflight.py` already drives.

The one filesystem write in this whole script is the markdown report file itself (an artifact,
not application/DB state).

Usage:
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_predictive_signal_audit.py
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_predictive_signal_audit.py --no-preflight
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/run_predictive_signal_audit.py --output docs/market_matrix_report.md
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_predictive_signal_audit_service, get_engine
from modules.predictions.domain.market_audit import MarketAuditRecord
from modules.predictions.infrastructure.persistence.repositories import SqlAlchemyMarketRepository


def _best_scores(record: MarketAuditRecord) -> tuple[float | None, float | None]:
    """Best baseline score vs. best non-baseline (ML) score from candidate_scores — a
    presentation-layer derivation, never stored on the domain record itself."""
    baseline_algos = set(record.baseline_candidate_algorithms)
    baseline_scores = [v for k, v in record.candidate_scores.items() if k in baseline_algos]
    ml_scores = [v for k, v in record.candidate_scores.items() if k not in baseline_algos]
    lower_is_better = record.ranking_metric in {"log_loss", "mae"}
    pick = min if lower_is_better else max
    best_baseline = pick(baseline_scores) if baseline_scores else None
    best_ml = pick(ml_scores) if ml_scores else None
    return best_baseline, best_ml


def _row(record: MarketAuditRecord) -> str:
    best_baseline, best_ml = _best_scores(record)
    preflight = "n/a (--no-preflight)" if record.preflight_ready is None else ("READY" if record.preflight_ready else "BLOCKED")
    return "| {sport} | {market} | {target} | {samples} | {features} | {preflight} | {champ} | {algo} | {baseline} | {ml} | {preds} | {outcomes} |".format(
        sport=record.sport_code,
        market=record.market_key,
        target=record.target_type.value,
        samples=record.sample_count if record.sample_count is not None else "-",
        features=record.feature_count if record.feature_count is not None else "-",
        preflight=preflight,
        champ=record.champion_model_key or "-",
        algo=record.champion_algorithm or "-",
        baseline=f"{best_baseline:.4f}" if best_baseline is not None else "-",
        ml=f"{best_ml:.4f}" if best_ml is not None else "-",
        preds=record.prediction_count if record.prediction_count is not None else "-",
        outcomes=record.outcome_count if record.outcome_count is not None else "-",
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--no-preflight", action="store_true",
        help="skip TrainingPreflightService.check() (cheap mode — matrix's own numbers are always cheap regardless)",
    )
    parser.add_argument("--output", default="docs/market_matrix_report.md", help="markdown report path")
    args = parser.parse_args()

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    now = datetime.now(timezone.utc)

    async with session_factory() as session:
        service = build_predictive_signal_audit_service(session)
        markets = await SqlAlchemyMarketRepository(session=session).list_all()
        markets = sorted(markets, key=lambda m: (m.sport_code, m.market_key))

        records: list[MarketAuditRecord] = []
        for i, market in enumerate(markets, 1):
            print(f"[{i}/{len(markets)}] auditing {market.market_key}...", flush=True)
            record = await service.audit_market(market.market_key, now, include_preflight=not args.no_preflight)
            records.append(record)

    ready_count = sum(1 for r in records if r.preflight_ready)
    champion_count = sum(1 for r in records if r.champion_model_key is not None)
    zero_sample_count = sum(1 for r in records if not r.sample_count)

    lines = [
        "# TitanIQ Predictive Signal Recovery — Market Matrix (Phase 1)",
        "",
        f"Generated {now.isoformat()}. {len(records)} markets audited"
        + (" (preflight skipped via --no-preflight)." if args.no_preflight else "."),
        "",
        f"- Preflight READY: {ready_count}/{len(records)}" if not args.no_preflight else "- Preflight: n/a (--no-preflight)",
        f"- Markets with a Champion: {champion_count}/{len(records)}",
        f"- Markets with zero samples in the latest persisted dataset: {zero_sample_count}/{len(records)}",
        "",
        "| Sport | Market | Target | Samples | Features | Preflight | Champion | Algorithm | "
        "Best Baseline | Best ML | Predictions | Outcomes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(_row(r) for r in records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\n{ready_count}/{len(records)} market(s) READY for training." if not args.no_preflight else "")
    print(f"{champion_count}/{len(records)} market(s) have a Champion.")
    print(f"{zero_sample_count}/{len(records)} market(s) have zero samples in the latest persisted dataset.")
    print(f"\nReport written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
