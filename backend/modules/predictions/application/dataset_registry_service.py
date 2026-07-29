"""Dataset Registry — versioning + approval workflow + drift detection (Milestone 9.1 Dataset
Platform). Mirrors `MarketRegistryService`'s lifecycle-gate shape (Milestone 9): this service
enforces valid state transitions and single-latest-version bookkeeping, it does not re-derive
whether a dataset *should* be approved (a human/`quality_issues` call, made before `validate()`/
`approve()` is invoked).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.predictions.domain.dataset import Dataset, DatasetId, DatasetQualityIssue, DatasetStatus
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.dataset_repository import DatasetRepositoryPort

_DRIFT_ALERT_THRESHOLD = 0.2  # |mean_a - mean_b| / (|mean_a| + eps) above this flags feature drift


class DatasetNotFoundError(KeyError):
    pass


class InvalidDatasetLifecycleTransitionError(ValueError):
    pass


class DatasetHasQualityIssuesError(ValueError):
    pass


@dataclass
class DatasetRegistryService:
    datasets: DatasetRepositoryPort

    async def register(self, dataset: Dataset) -> Dataset:
        return await self.datasets.upsert(dataset)

    async def validate(self, dataset_id: DatasetId) -> Dataset:
        dataset = await self._require(dataset_id)
        if dataset.status is not DatasetStatus.DRAFT:
            raise InvalidDatasetLifecycleTransitionError(
                f"cannot validate dataset v{dataset.version} from {dataset.status.value} — must be DRAFT"
            )
        if DatasetQualityIssue.TOO_FEW_SAMPLES in dataset.quality_issues:
            raise DatasetHasQualityIssuesError(
                f"dataset v{dataset.version} has {DatasetQualityIssue.TOO_FEW_SAMPLES.value} — cannot validate"
            )
        dataset.status = DatasetStatus.VALIDATED
        return await self.datasets.upsert(dataset)

    async def approve(self, dataset_id: DatasetId, approved_by: str, now: datetime) -> Dataset:
        dataset = await self._require(dataset_id)
        if dataset.status is not DatasetStatus.VALIDATED:
            raise InvalidDatasetLifecycleTransitionError(
                f"cannot approve dataset v{dataset.version} from {dataset.status.value} — must be VALIDATED"
            )
        dataset.status = DatasetStatus.APPROVED
        dataset.approved_by = approved_by
        dataset.approved_at = now
        return await self.datasets.upsert(dataset)

    async def archive(self, dataset_id: DatasetId) -> Dataset:
        dataset = await self._require(dataset_id)
        if dataset.status is DatasetStatus.ARCHIVED:
            raise InvalidDatasetLifecycleTransitionError(f"dataset v{dataset.version} is already ARCHIVED")
        dataset.status = DatasetStatus.ARCHIVED
        return await self.datasets.upsert(dataset)

    async def detect_drift(self, market_id: MarketId, baseline_id: DatasetId | None = None) -> dict:
        """Compares the latest dataset for ``market_id`` against ``baseline_id`` (or the
        second-most-recent version, if omitted) — relative mean shift per shared feature."""
        latest = await self.datasets.get_latest_version(market_id)
        if latest is None:
            return {"drift_detected": False, "reason": "no dataset built yet"}

        if baseline_id is not None:
            baseline = await self.datasets.get(baseline_id)
        else:
            versions = await self.datasets.list_by_market(market_id, limit=2)
            baseline = next((d for d in versions if d.id != latest.id), None)

        if baseline is None:
            return {"drift_detected": False, "reason": "no baseline dataset to compare against"}

        drifted_features = {}
        for key, latest_mean in latest.statistics.mean.items():
            baseline_mean = baseline.statistics.mean.get(key)
            if baseline_mean is None:
                continue
            denominator = abs(baseline_mean) + 1e-6
            relative_shift = abs(latest_mean - baseline_mean) / denominator
            if relative_shift >= _DRIFT_ALERT_THRESHOLD:
                drifted_features[key] = relative_shift

        return {
            "drift_detected": bool(drifted_features),
            "baseline_version": baseline.version,
            "latest_version": latest.version,
            "drifted_features": drifted_features,
        }

    async def _require(self, dataset_id: DatasetId) -> Dataset:
        dataset = await self.datasets.get(dataset_id)
        if dataset is None:
            raise DatasetNotFoundError(str(dataset_id))
        return dataset
