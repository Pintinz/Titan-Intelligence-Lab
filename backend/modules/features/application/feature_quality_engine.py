"""Feature Quality Intelligence (docs/feature_catalog.md, Feature Quality Intelligence).

Mirrors the shape of modules.admin.application.health_intelligence_engine.HealthIntelligenceEngine
deliberately: windowed metrics computed on demand from append-only history (never
pre-aggregated), a persisted report type for point-in-time verdicts, and every score documented
with its formula and weights rather than left as a magic number.

Two things this module is explicit about NOT doing yet:
  - "Null %" and "Missing Value %" are computed identically today — `FeatureValue.value` has no
    explicit null representation, only `QualityFlag.MISSING_IMPUTED` at write time. They'll
    diverge once the domain model supports an explicit null distinct from "imputed" (see
    docs/decisions.md ADR-017).
  - "Storage Size" is an estimate (JSON-encoded value size + a fixed per-row overhead), not a
    live `pg_total_relation_size` query — accurate once there's a real Postgres to query against
    (docs/decisions.md ADR-018).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from uuid import uuid4

from modules.features.domain.entities import (
    FeatureComputationLog,
    FeatureConsumer,
    FeatureUsageRecord,
    FeatureValidationReport,
    FeatureValue,
)
from modules.features.domain.freshness import FreshnessStatus, classify_freshness
from modules.features.domain.value_objects import (
    FeatureKey,
    FeatureValidationReportId,
    QualityFlag,
    ValidationStatus,
)
from modules.features.ports.provider_reliability import ProviderReliabilityPort
from modules.features.ports.repositories import (
    FeatureComputationLogRepositoryPort,
    FeatureConsumerRepositoryPort,
    FeatureDefinitionRepositoryPort,
    FeatureUsageRepositoryPort,
    FeatureValidationReportRepositoryPort,
    FeatureValueRepositoryPort,
)

DEFAULT_VALIDATION_WINDOW = timedelta(days=7)
DEFAULT_COMPUTATION_WINDOW = timedelta(days=30)
FRESHNESS_STALE_MULTIPLIER = 5  # freshness hits 0 at (ttl * this) seconds of age
COMPUTATION_COST_CEILING_MS = 5000.0  # duration at/above this scores 100 on the cost scale
LOW_QUALITY_ADVISORY_THRESHOLD = 50.0  # below this, deprecation_warning() advises review
ROW_OVERHEAD_BYTES = 128  # rough per-row index/timestamp/id overhead, see ADR-018


class FeatureNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class FeatureQualitySnapshot:
    sample_size: int
    quality_score: float | None
    freshness_score: float | None
    reliability_score: float | None
    completeness_score: float | None
    missing_pct: float | None
    outlier_pct: float | None
    null_pct: float | None
    invalid_pct: float | None
    duplicate_pct: float | None
    coverage_pct: float | None
    # spec §26 "Context Freshness" — the real CURRENT/STALE/UNKNOWN verdict derived from
    # `freshness_score` (never independently invented), so a caller renders a categorical status
    # rather than reimplementing this same "score >= 1.0" threshold itself.
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN


@dataclass(frozen=True)
class ComputationCostSnapshot:
    sample_size: int
    average_duration_ms: float | None
    average_memory_bytes: float | None
    cost_score: float | None  # 0-100, normalized against COMPUTATION_COST_CEILING_MS


@dataclass(frozen=True)
class FeatureHealthReport:
    feature_key: str
    status: str
    quality: FeatureQualitySnapshot
    last_validation: FeatureValidationReport | None
    provider_source: str | None
    provider_reliability: float | None
    computation_cost: ComputationCostSnapshot
    storage_size_bytes: int | None
    consumer_count: int
    usage_last_7_days: int
    deprecation_warning: str | None


def _pct(count: int, total: int) -> float | None:
    return None if total == 0 else round(count / total * 100, 2)


@dataclass
class FeatureQualityEngine:
    definitions: FeatureDefinitionRepositoryPort
    values: FeatureValueRepositoryPort
    reports: FeatureValidationReportRepositoryPort
    computation_logs: FeatureComputationLogRepositoryPort
    consumers: FeatureConsumerRepositoryPort
    usage: FeatureUsageRepositoryPort
    provider_reliability_port: ProviderReliabilityPort | None = None
    quality_weight_reliability: float = 0.35
    quality_weight_freshness: float = 0.35
    quality_weight_completeness: float = 0.30

    async def _require_definition(self, feature_key: str | FeatureKey):
        key = feature_key if isinstance(feature_key, FeatureKey) else FeatureKey(feature_key)
        definition = await self.definitions.get(key)
        if definition is None:
            raise FeatureNotFoundError(str(key))
        return definition

    # -- quality snapshot -----------------------------------------------------------------------

    async def quality_snapshot(
        self,
        feature_key: str,
        now: datetime,
        *,
        window: timedelta = DEFAULT_VALIDATION_WINDOW,
        total_expected_entities: int | None = None,
    ) -> FeatureQualitySnapshot:
        definition = await self._require_definition(feature_key)
        key = definition.feature_key
        values = await self.values.list_all_recent(key, since=now - window)
        total = len(values)

        if total == 0:
            return FeatureQualitySnapshot(0, None, None, None, None, None, None, None, None, None, None)

        outlier_count = sum(1 for v in values if QualityFlag.OUT_OF_RANGE in v.quality_flags)
        invalid_count = sum(1 for v in values if QualityFlag.TYPE_MISMATCH in v.quality_flags)
        missing_count = sum(1 for v in values if QualityFlag.MISSING_IMPUTED in v.quality_flags)
        ok_count = sum(1 for v in values if v.quality_flags == (QualityFlag.OK,))

        seen: dict[tuple, int] = {}
        for v in values:
            k = (v.entity_type, v.entity_id, v.as_of)
            seen[k] = seen.get(k, 0) + 1
        duplicate_count = sum(c - 1 for c in seen.values() if c > 1)

        missing_pct = _pct(missing_count, total)
        outlier_pct = _pct(outlier_count, total)
        invalid_pct = _pct(invalid_count, total)
        null_pct = missing_pct  # documented equivalence, see module docstring / ADR-017
        duplicate_pct = _pct(duplicate_count, total)

        coverage_pct = None
        if total_expected_entities:
            distinct_entities = {v.entity_id for v in values}
            coverage_pct = round(len(distinct_entities) / total_expected_entities * 100, 2)

        reliability_score = _pct(ok_count, total)

        most_recent = max(values, key=lambda v: v.as_of)
        freshness_score = self._freshness_score(most_recent.as_of, now, definition.online_ttl_seconds)

        completeness_score = (
            coverage_pct if coverage_pct is not None else round(100 - (missing_pct or 0), 2)
        )

        quality_score = round(
            self.quality_weight_reliability * (reliability_score or 0)
            + self.quality_weight_freshness * (freshness_score * 100 if freshness_score is not None else 0)
            + self.quality_weight_completeness * completeness_score,
            2,
        )

        freshness_score_pct = round(freshness_score * 100, 2) if freshness_score is not None else None
        return FeatureQualitySnapshot(
            sample_size=total,
            quality_score=quality_score,
            freshness_score=freshness_score_pct,
            reliability_score=reliability_score,
            completeness_score=completeness_score,
            missing_pct=missing_pct,
            outlier_pct=outlier_pct,
            null_pct=null_pct,
            invalid_pct=invalid_pct,
            duplicate_pct=duplicate_pct,
            coverage_pct=coverage_pct,
            freshness_status=classify_freshness(freshness_score_pct),
        )

    @staticmethod
    def _freshness_score(most_recent_as_of: datetime, now: datetime, ttl_seconds: int) -> float:
        """1.0 while the freshest value is within its TTL; decays linearly to 0.0 by
        ``ttl_seconds * FRESHNESS_STALE_MULTIPLIER`` — "definitely stale" rather than an
        instant cliff at the TTL boundary, matching how a cache actually degrades in usefulness."""
        age = max(0.0, (now - most_recent_as_of).total_seconds())
        if age <= ttl_seconds:
            return 1.0
        stale_at = ttl_seconds * FRESHNESS_STALE_MULTIPLIER
        if stale_at <= ttl_seconds:
            return 0.0
        return max(0.0, 1 - (age - ttl_seconds) / (stale_at - ttl_seconds))

    # -- validation reports -----------------------------------------------------------------------

    async def run_validation(
        self,
        feature_key: str,
        now: datetime,
        *,
        window: timedelta = DEFAULT_VALIDATION_WINDOW,
        total_expected_entities: int | None = None,
    ) -> FeatureValidationReport:
        definition = await self._require_definition(feature_key)
        snapshot = await self.quality_snapshot(
            feature_key, now, window=window, total_expected_entities=total_expected_entities
        )

        issues: list[str] = []
        if snapshot.sample_size == 0:
            issues.append(f"no feature values recorded in the last {window}")
        else:
            if (snapshot.missing_pct or 0) > 10:
                issues.append(f"missing value rate {snapshot.missing_pct}% exceeds 10%")
            if (snapshot.outlier_pct or 0) > 5:
                issues.append(f"outlier rate {snapshot.outlier_pct}% exceeds 5%")
            if (snapshot.invalid_pct or 0) > 0:
                issues.append(f"invalid (type-mismatched) values present: {snapshot.invalid_pct}%")
            if (snapshot.duplicate_pct or 0) > 0:
                issues.append(f"duplicate values present: {snapshot.duplicate_pct}%")
            if snapshot.freshness_score is not None and snapshot.freshness_score < 50:
                issues.append(f"freshness score {snapshot.freshness_score} below 50")

        if snapshot.sample_size == 0 or (snapshot.quality_score or 0) < 30:
            status = ValidationStatus.FAILED
        elif issues:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.PASSED

        report = FeatureValidationReport(
            id=FeatureValidationReportId(uuid4()),
            feature_key=definition.feature_key,
            validated_at=now,
            sample_size=snapshot.sample_size,
            quality_score=snapshot.quality_score,
            freshness_score=snapshot.freshness_score,
            reliability_score=snapshot.reliability_score,
            completeness_score=snapshot.completeness_score,
            missing_pct=snapshot.missing_pct,
            outlier_pct=snapshot.outlier_pct,
            null_pct=snapshot.null_pct,
            invalid_pct=snapshot.invalid_pct,
            duplicate_pct=snapshot.duplicate_pct,
            coverage_pct=snapshot.coverage_pct,
            status=status,
            issues=tuple(issues),
        )
        return await self.reports.record(report)

    async def get_latest_validation(self, feature_key: str) -> FeatureValidationReport | None:
        definition = await self._require_definition(feature_key)
        return await self.reports.get_latest(definition.feature_key)

    async def list_validation_history(self, feature_key: str, limit: int = 50) -> list[FeatureValidationReport]:
        definition = await self._require_definition(feature_key)
        return await self.reports.list_by_feature(definition.feature_key, limit=limit)

    # -- provider source / reliability ----------------------------------------------------------

    async def provider_reliability(self, feature_key: str, now: datetime) -> float | None:
        definition = await self._require_definition(feature_key)
        if definition.source_provider_key is None or self.provider_reliability_port is None:
            return None
        return await self.provider_reliability_port.reliability_score(definition.source_provider_key, now)

    # -- computation cost ------------------------------------------------------------------------

    async def record_computation(
        self, feature_key: str, now: datetime, duration_ms: float, memory_bytes: int | None = None
    ) -> FeatureComputationLog:
        definition = await self._require_definition(feature_key)
        log = FeatureComputationLog(
            feature_key=definition.feature_key, recorded_at=now, duration_ms=duration_ms, memory_bytes=memory_bytes
        )
        return await self.computation_logs.record(log)

    async def computation_cost(
        self, feature_key: str, now: datetime, window: timedelta = DEFAULT_COMPUTATION_WINDOW
    ) -> ComputationCostSnapshot:
        definition = await self._require_definition(feature_key)
        logs = await self.computation_logs.list_since(definition.feature_key, now - window)
        if not logs:
            return ComputationCostSnapshot(0, None, None, None)

        avg_duration = mean(log.duration_ms for log in logs)
        memory_samples = [log.memory_bytes for log in logs if log.memory_bytes is not None]
        avg_memory = mean(memory_samples) if memory_samples else None
        cost_score = round(min(100.0, avg_duration / COMPUTATION_COST_CEILING_MS * 100), 2)

        return ComputationCostSnapshot(
            sample_size=len(logs), average_duration_ms=round(avg_duration, 3),
            average_memory_bytes=avg_memory, cost_score=cost_score,
        )

    # -- storage size (estimate — see ADR-018) ----------------------------------------------------

    async def storage_size_bytes(
        self, feature_key: str, now: datetime, window: timedelta | None = None
    ) -> int | None:
        definition = await self._require_definition(feature_key)
        since = (now - window) if window else None
        values = await self.values.list_all_recent(definition.feature_key, since=since)
        if not values:
            return None
        return sum(len(json.dumps({"value": v.value})) + ROW_OVERHEAD_BYTES for v in values)

    # -- consumers --------------------------------------------------------------------------------

    async def register_consumer(self, feature_key: str, consumer_key: str, now: datetime) -> FeatureConsumer:
        definition = await self._require_definition(feature_key)
        consumer = FeatureConsumer(feature_key=definition.feature_key, consumer_key=consumer_key, registered_at=now)
        return await self.consumers.register(consumer)

    async def list_consumers(self, feature_key: str) -> list[FeatureConsumer]:
        definition = await self._require_definition(feature_key)
        return await self.consumers.list_by_feature(definition.feature_key)

    # -- usage frequency --------------------------------------------------------------------------

    async def record_usage(self, feature_key: str, now: datetime) -> None:
        definition = await self._require_definition(feature_key)
        window_key = now.date().isoformat()
        record = await self.usage.get(definition.feature_key, window_key) or FeatureUsageRecord(
            feature_key=definition.feature_key, window_key=window_key
        )
        record.read_count += 1
        await self.usage.upsert(record)

    async def usage_frequency(self, feature_key: str, now: datetime, window_days: int = 7) -> int:
        definition = await self._require_definition(feature_key)
        since_key = (now - timedelta(days=window_days)).date().isoformat()
        records = await self.usage.list_since(definition.feature_key, since_key)
        return sum(r.read_count for r in records)

    # -- deprecation warning ----------------------------------------------------------------------

    async def deprecation_warning(self, feature_key: str, now: datetime) -> str | None:
        definition = await self._require_definition(feature_key)
        if definition.status.value == "deprecated":
            when = definition.deprecated_at.isoformat() if definition.deprecated_at else "an unrecorded date"
            return f"Feature deprecated since {when} — scheduled for removal, do not add new consumers."

        latest = await self.reports.get_latest(definition.feature_key)
        if latest is not None and latest.quality_score is not None and latest.quality_score < LOW_QUALITY_ADVISORY_THRESHOLD:
            return (
                f"Quality score {latest.quality_score} is below the {LOW_QUALITY_ADVISORY_THRESHOLD} "
                "advisory threshold as of the last validation — consider reviewing this feature."
            )
        return None

    # -- composite health report ------------------------------------------------------------------

    async def health_report(
        self, feature_key: str, now: datetime, *, total_expected_entities: int | None = None
    ) -> FeatureHealthReport:
        definition = await self._require_definition(feature_key)
        quality = await self.quality_snapshot(feature_key, now, total_expected_entities=total_expected_entities)
        return FeatureHealthReport(
            feature_key=definition.feature_key.value,
            status=definition.status.value,
            quality=quality,
            last_validation=await self.reports.get_latest(definition.feature_key),
            provider_source=definition.source_provider_key,
            provider_reliability=await self.provider_reliability(feature_key, now),
            computation_cost=await self.computation_cost(feature_key, now),
            storage_size_bytes=await self.storage_size_bytes(feature_key, now),
            consumer_count=len(await self.consumers.list_by_feature(definition.feature_key)),
            usage_last_7_days=await self.usage_frequency(feature_key, now, window_days=7),
            deprecation_warning=await self.deprecation_warning(feature_key, now),
        )
