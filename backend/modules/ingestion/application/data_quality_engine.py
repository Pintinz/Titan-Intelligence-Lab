"""Ingestion-level Data Quality Engine (docs/roadmap.md Milestone 5).

Scores *raw ingested sports data* — distinct from
``modules.features.application.feature_quality_engine.FeatureQualityEngine``, which scores
*derived ML features* (docs/decisions.md). Mirrors that engine's shape deliberately: windowed
metrics, a persisted report entity, documented weights instead of unexplained magic numbers.

``accuracy_pct`` is computed identically to ``validity_pct`` today — true accuracy would need an
independent ground truth to compare against (a second provider, or a manual audit), which
doesn't exist yet. This is a documented proxy, not a real distinction, same spirit as
FeatureQualityEngine's null_pct/missing_pct equivalence (docs/decisions.md ADR-017).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.features.ports.provider_reliability import ProviderReliabilityPort
from modules.ingestion.domain.entities import DataQualityReport
from modules.ingestion.domain.value_objects import DataQualityReportId, EntityKind, SyncStatus
from modules.ingestion.ports.repositories import DataQualityReportRepositoryPort, SyncRunRepositoryPort

FRESHNESS_STALE_MULTIPLIER = 5
_RUN_HISTORY_LOOKBACK = 50


def _pct(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else round(numerator / denominator * 100, 2)


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — every datetime
    in this codebase is UTC by convention, so a naive value read back from storage is assumed
    to be UTC and stamped to match ``reference``'s awareness before comparison. Real Postgres/
    asyncpg preserves tzinfo correctly; this only bites in the SQLite testing path, but the
    engine needs to not crash regardless of which database produced the row."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class IngestionQualityEngine:
    sync_runs: SyncRunRepositoryPort
    reports: DataQualityReportRepositoryPort
    provider_quality_port: ProviderReliabilityPort | None = None

    async def generate_report(
        self,
        sport_code: str,
        entity_kind: EntityKind,
        now: datetime,
        *,
        sample_size: int,
        missing_count: int = 0,
        invalid_count: int = 0,
        relationship_issue_count: int = 0,
        duplicate_count: int = 0,
        expected_update_frequency_seconds: int = 86400,
        total_expected_records: int | None = None,
        provider_key: str | None = None,
        reliability_window_days: int = 7,
    ) -> DataQualityReport:
        completeness_pct = _pct(max(0, sample_size - missing_count), sample_size)
        consistency_pct = _pct(max(0, sample_size - relationship_issue_count - duplicate_count), sample_size)
        validity_pct = _pct(max(0, sample_size - invalid_count), sample_size)
        accuracy_pct = validity_pct

        freshness_score = await self._freshness_score(sport_code, entity_kind, now, expected_update_frequency_seconds)
        reliability_score = await self._reliability_from_recent_runs(
            sport_code, entity_kind, now, reliability_window_days
        )
        coverage_pct = _pct(sample_size, total_expected_records) if total_expected_records else None
        provider_quality_score = (
            await self.provider_quality_port.reliability_score(provider_key, now)
            if provider_key and self.provider_quality_port
            else None
        )

        components = [c for c in (consistency_pct, freshness_score, completeness_pct, reliability_score) if c is not None]
        quality_score = round(sum(components) / len(components), 2) if components else None

        issues: list[str] = []
        if missing_count:
            issues.append(f"{missing_count} record(s) with missing required fields")
        if invalid_count:
            issues.append(f"{invalid_count} record(s) with invalid values")
        if relationship_issue_count:
            issues.append(f"{relationship_issue_count} record(s) with relationship/FK issues")
        if duplicate_count:
            issues.append(f"{duplicate_count} duplicate record(s) detected in the batch")

        report = DataQualityReport(
            id=DataQualityReportId(uuid4()),
            sport_code=sport_code,
            entity_kind=entity_kind,
            generated_at=now,
            sample_size=sample_size,
            completeness_pct=completeness_pct,
            consistency_pct=consistency_pct,
            freshness_score=freshness_score,
            accuracy_pct=accuracy_pct,
            validity_pct=validity_pct,
            reliability_score=reliability_score,
            coverage_pct=coverage_pct,
            provider_quality_score=provider_quality_score,
            quality_score=quality_score,
            issues=tuple(issues),
        )
        return await self.reports.record(report)

    async def get_latest(self, sport_code: str, entity_kind: EntityKind) -> DataQualityReport | None:
        return await self.reports.get_latest(sport_code, entity_kind)

    async def list_history(self, sport_code: str, entity_kind: EntityKind, limit: int = 50) -> list[DataQualityReport]:
        return await self.reports.list_by_entity_kind(sport_code, entity_kind, limit=limit)

    async def _freshness_score(
        self, sport_code: str, entity_kind: EntityKind, now: datetime, ttl_seconds: int
    ) -> float | None:
        """1.0 (as 100) while the most recent successful sync is within ``ttl_seconds`` old;
        decays linearly to 0 by ``ttl_seconds * FRESHNESS_STALE_MULTIPLIER`` — same formula as
        FeatureQualityEngine._freshness_score, applied to sync recency instead of feature-value
        recency."""
        runs = await self.sync_runs.list_recent(sport_code, entity_kind, limit=_RUN_HISTORY_LOOKBACK)
        successful = [r for r in runs if r.status in (SyncStatus.SUCCEEDED, SyncStatus.PARTIAL) and r.finished_at]
        if not successful:
            return None
        most_recent = max(successful, key=lambda r: r.finished_at)
        age = max(0.0, (now - _ensure_aware(most_recent.finished_at, now)).total_seconds())
        if age <= ttl_seconds:
            return 100.0
        stale_at = ttl_seconds * FRESHNESS_STALE_MULTIPLIER
        if stale_at <= ttl_seconds:
            return 0.0
        return round(max(0.0, 1 - (age - ttl_seconds) / (stale_at - ttl_seconds)) * 100, 2)

    async def _reliability_from_recent_runs(
        self, sport_code: str, entity_kind: EntityKind, now: datetime, window_days: int
    ) -> float | None:
        runs = await self.sync_runs.list_recent(sport_code, entity_kind, limit=_RUN_HISTORY_LOOKBACK)
        cutoff = now - timedelta(days=window_days)
        recent = [r for r in runs if _ensure_aware(r.started_at, cutoff) >= cutoff]
        if not recent:
            return None
        successes = sum(1 for r in recent if r.status in (SyncStatus.SUCCEEDED, SyncStatus.PARTIAL))
        return round(successes / len(recent) * 100, 2)
