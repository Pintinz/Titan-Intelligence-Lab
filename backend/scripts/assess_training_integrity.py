"""Contaminated Model Policy (forensic audit §10, Critical Fix #1 follow-up).

`scripts/scan_feature_leakage.py` proves WHICH feature-store rows were computed after their own
fixture's kickoff. This script answers the next question: which currently-registered CHAMPION
models actually consumed one of those contaminated feature keys, and therefore cannot be trusted
without a clean retrain.

Method — real cross-referencing, not a blanket "everything old is suspect":
  1. Run the leakage scan to get the set of contaminated feature KEYS (not just fixtures).
  2. For every PRODUCTION market, read its real Feature-to-Market Registry mapping
     (`FeatureMarketMappingService.list_for_market` — the same registry
     `PredictionContextBuilder` resolves a live feature snapshot through).
  3. A market's CHAMPION is flagged only if it is genuinely trained (`is_genuinely_trained()` —
     has a real fitted artifact, not a placeholder) AND at least one feature key actually mapped
     to that market appears in the contaminated set. A market that never consumes a contaminated
     feature is left alone, even if other markets' features are contaminated.

Writing `provenance_status = "PROVENANCE_COMPROMISED"` is exactly what
`ModelRegistryService.promote_to_champion` now checks (`TrainingIntegrityError`) before allowing
a promotion — see that module's docstring. This script never invents "PROVENANCE_VERIFIED"; a
model this run does NOT flag stays at whatever `provenance_status` it already had (almost always
the honest default, "PROVENANCE_UNVERIFIED" — "not proven contaminated" is not the same claim as
"proven clean").

Marking a model compromised does NOT retire it — a flagged Champion keeps serving live
predictions exactly as before; the only behavioral change is that it (or any other CHALLENGER
this script later flags) can no longer be *promoted* while compromised. Whether to also pull an
already-compromised Champion back to formula fallback right now is a separate, real product
decision this script deliberately does not make — see the printed report's own note.

Defaults to a dry run (report only). Pass --apply to actually write provenance_status.

Usage:
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/assess_training_integrity.py
    TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/assess_training_integrity.py --apply
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.infrastructure.persistence.repositories import (
    SqlAlchemyMarketRepository,
    SqlAlchemyModelRepository,
)
import apps.api.composition as composition

from scan_feature_leakage import scan as scan_leakage

COMPROMISED = "PROVENANCE_COMPROMISED"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write provenance_status=PROVENANCE_COMPROMISED (default: dry run)")
    args = parser.parse_args()

    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        violations = await scan_leakage(session)
        contaminated_features = {v.feature_key for v in violations}
        print(f"Contaminated feature keys ({len(contaminated_features)}): {sorted(contaminated_features)}\n")

        markets_repo = SqlAlchemyMarketRepository(session=session)
        models_repo = SqlAlchemyModelRepository(session=session)
        mapping_service = composition.build_feature_market_mapping_service(session)

        markets = await markets_repo.list_by_status(MarketStatus.PRODUCTION)

        flagged: list[tuple[str, str, set[str]]] = []
        already_flagged: list[str] = []
        clean_or_untrained: list[tuple[str, str]] = []

        for market in markets:
            champion = await models_repo.get_champion(market.id)
            if champion is None:
                continue
            if not champion.is_genuinely_trained():
                clean_or_untrained.append((market.market_key, "no real artifact (formula/placeholder — not applicable)"))
                continue

            mappings = await mapping_service.list_for_market(market.market_key)
            market_features = {m.feature_key for m in mappings}
            overlap = market_features & contaminated_features

            if not overlap:
                clean_or_untrained.append((market.market_key, "genuinely trained, no contaminated feature in its mapping"))
                continue

            if champion.is_training_compromised():
                already_flagged.append(market.market_key)
                continue

            flagged.append((market.market_key, champion.model_key, overlap))
            if args.apply:
                champion.provenance_status = COMPROMISED
                await models_repo.upsert(champion)

        print(f"{'APPLIED' if args.apply else 'DRY RUN'} — {len(flagged)} champion(s) newly flagged PROVENANCE_COMPROMISED:")
        for market_key, model_key, overlap in flagged:
            print(f"  {market_key:50s} model={model_key:45s} via={sorted(overlap)}")

        if already_flagged:
            print(f"\n{len(already_flagged)} champion(s) already PROVENANCE_COMPROMISED (unchanged): {already_flagged}")

        print(f"\n{len(clean_or_untrained)} market(s) left untouched (no genuinely-trained champion, or no contaminated feature in its mapping):")
        for market_key, reason in clean_or_untrained:
            print(f"  {market_key:50s} {reason}")

        if args.apply:
            await session.commit()
            print("\nCommitted.")
        else:
            print("\nDRY RUN — nothing written. Re-run with --apply to persist provenance_status.")

        print(
            "\nNote: flagging PROVENANCE_COMPROMISED blocks future promotion of this model "
            "(ModelRegistryService.promote_to_champion now refuses it). It does NOT retire an "
            "already-serving Champion or force it to formula fallback — that is a separate, "
            "explicit decision, not made by this script."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
