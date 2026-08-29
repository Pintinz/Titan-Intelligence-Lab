"""Champion artifact health audit (Production Integrity Hardening, 2026-08-29) — extracted from
`apps/api/main.py`'s `GET /api/v1/admin/system/model-health` so the exact same classification
logic is also reusable by `modules.predictions.infrastructure.celery.tasks.repair_broken_champions_task`,
rather than a second, drifting copy. A registry row saying CHAMPION is not evidence the artifact it
points at is actually loadable — a real production incident the same day (40 of 53 PRODUCTION
markets' Champions pointed at artifacts that were never durably uploaded) took manual log
archaeology to even enumerate. Runs `ModelLoaderService.load()` — the exact same fetch/checksum/
deserialize path a real prediction request takes — against every PRODUCTION market's Champion,
through a throwaway loader instance (never the shared serving cache), so this is entirely
read-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from modules.predictions.domain.entities import MarketDefinition, ModelDefinition
from modules.predictions.domain.value_objects import MarketStatus
from modules.predictions.infrastructure.ml.model_loader import (
    ArtifactIntegrityError,
    ModelLoaderService,
    UnknownModelFrameworkError,
)
from modules.predictions.infrastructure.ml.supabase_artifact_store import ArtifactStoreError
from modules.predictions.ports.ml_model import ModelArtifactStorePort
from modules.predictions.ports.repositories import MarketRepositoryPort, ModelRepositoryPort

# Every status a Champion audit entry can land in. HEALTHY is the only one a real prediction
# request can actually serve from; everything else means that market is silently falling back to
# the statistical baseline right now, regardless of what its registry row claims.
HEALTHY = "HEALTHY"
NO_CHAMPION = "NO_CHAMPION"
INVALID_CHAMPION = "INVALID_CHAMPION"
CORRUPT_ARTIFACT = "CORRUPT_ARTIFACT"
MISSING_ARTIFACT = "MISSING_ARTIFACT"
LEGACY_LOCAL_ONLY = "LEGACY_LOCAL_ONLY"
UNKNOWN_FAILURE = "UNKNOWN_FAILURE"
RUNTIME_LOAD_FAILED = "RUNTIME_LOAD_FAILED"

# The subset `repair_broken_champion` can actually act on — INVALID_CHAMPION (a deliberate
# never-trained placeholder) and UNKNOWN_FAILURE (an unrecognized framework string, a real data
# problem no retrain fixes) are excluded on purpose; see their own module's docstrings.
REPAIRABLE_STATUSES = frozenset({NO_CHAMPION, MISSING_ARTIFACT, CORRUPT_ARTIFACT, LEGACY_LOCAL_ONLY, RUNTIME_LOAD_FAILED})


@dataclass
class ChampionHealthEntry:
    market: MarketDefinition
    status: str
    champion: ModelDefinition | None = None
    error: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict:
        entry: dict = {"market_key": self.market.market_key, "status": self.status}
        if self.champion is not None:
            entry["model_id"] = str(self.champion.id.value)
            entry["version"] = self.champion.version
            entry["algorithm"] = self.champion.algorithm
            entry["framework"] = self.champion.framework
            entry["artifact_ref"] = self.champion.artifact_ref
            entry["promoted_at"] = self.champion.promoted_at.isoformat() if self.champion.promoted_at else None
        if self.error is not None:
            entry["error"] = self.error
        if self.detail is not None:
            entry["detail"] = self.detail
        return entry


@dataclass
class ModelHealthAuditService:
    markets: MarketRepositoryPort
    models: ModelRepositoryPort
    artifact_store: ModelArtifactStorePort

    async def audit_one(self, market: MarketDefinition) -> ChampionHealthEntry:
        champion = await self.models.get_champion(market.id)
        if champion is None:
            return ChampionHealthEntry(market=market, status=NO_CHAMPION)
        if not champion.is_genuinely_trained():
            return ChampionHealthEntry(
                market=market, status=INVALID_CHAMPION, champion=champion,
                detail="placeholder/never-trained Champion (artifact_ref is None)",
            )

        loader = ModelLoaderService(artifact_store=self.artifact_store)
        try:
            await loader.load(
                champion.id, champion.framework, champion.algorithm, market.target_type,
                champion.artifact_ref, champion.artifact_checksum,
            )
            return ChampionHealthEntry(market=market, status=HEALTHY, champion=champion)
        except ArtifactIntegrityError as exc:
            return ChampionHealthEntry(market=market, status=CORRUPT_ARTIFACT, champion=champion, error=str(exc))
        except ArtifactStoreError as exc:
            return ChampionHealthEntry(market=market, status=MISSING_ARTIFACT, champion=champion, error=str(exc))
        except FileNotFoundError as exc:
            return ChampionHealthEntry(market=market, status=LEGACY_LOCAL_ONLY, champion=champion, error=str(exc))
        except UnknownModelFrameworkError as exc:
            return ChampionHealthEntry(market=market, status=UNKNOWN_FAILURE, champion=champion, error=str(exc))
        except Exception as exc:  # noqa: BLE001 — this audit's whole job is to catalogue every failure, not raise one
            return ChampionHealthEntry(market=market, status=RUNTIME_LOAD_FAILED, champion=champion, error=str(exc))

    async def audit_all_production_markets(self) -> list[ChampionHealthEntry]:
        markets = await self.markets.list_by_status(MarketStatus.PRODUCTION)
        return [await self.audit_one(market) for market in markets]
