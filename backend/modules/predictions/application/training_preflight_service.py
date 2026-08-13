"""Training Preflight Gate (Milestone 19 Phase 4). A read-only readiness gate a future Milestone
20 Challenger-training attempt must consult before training — mechanizes the parity/provenance
checks Milestone 19's audit (`docs/milestone19_preimplementation_audit.md` §16) established are
required for any market, re-run against live state rather than relying on a one-time snapshot.
Never trains a model, never writes anything: every check is a read, plus (where a `Dataset` is
needed) a call to the existing read-only `DatasetBuilder.build()`.

Maps onto the M19 master prompt's 16-item checklist as follows — most items map 1:1 onto a named
check below; a few genuinely collapse into one richer, honestly-computed check rather than being
artificially split, and three are per-observation architectural invariants (already code-verified
in the M19 audit) that this service cites rather than re-derives, since they aren't properties of
a bare `market_key`:

  market exists                        -> market_exists
  sufficient labeled observations      -> sufficient_labeled_observations
  labels valid                         -> labels_valid
  no temporal reference missing        -> temporal_reference_present
  temporal split valid                 -> temporal_split_valid
  feature set explicitly declared      -> feature_manifest_declared
  inference feature manifest known     -> feature_manifest_declared (the same manifest serves both)
  training feature versions known      -> feature_versions_known
  training/inference feature parity    -> training_inference_feature_parity
  required feature coverage acceptable -> required_feature_coverage_acceptable
  intelligence provenance valid        -> intelligence_feature_leakage_safe
  dataset reproducibility verified     -> dataset_reproducible
  dataset content hash generated       -> dataset_reproducible (same evidence)
  training dataset provenance complete -> dataset_provenance_persisted

  no post-kickoff information used         -> enforced per-event by
      `NewsMarketImpactEngine`/`news_provenance.is_information_available_before_kickoff`
      (M19 audit §7 item 4) — a property of individual news events at write time, not of a
      market_key; not re-derived here.
  no UNKNOWN_AVAILABILITY_TIME feature used -> enforced at feature-write time by
      `NewsEvent.is_feature_eligible()` and the lineup/transfer calculators' VERIFIED_PRE_MATCH
      gate (M19 audit §9-10); not re-derived here for the same reason.
  no unresolved historical membership used -> enforced by `HistoricalEntityResolutionService`
      (Transfer.effective_date chains only, never Player.team_id/KG PLAYS_FOR — M19 audit §11).

Those three are real, code-verified guarantees, not fabricated passes — but they're per-observation
invariants already enforced upstream, so this service reports the computable, market-scoped checks
and leaves those three as documented, cited architectural facts rather than claiming to re-verify
per-event data it never reads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from modules.features.domain.value_objects import FeatureKey
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.dataset_splitter import (
    InsufficientSamplesForSplitError,
    MissingTemporalReferenceError,
    split as split_dataset,
)
from modules.predictions.domain.dataset import Dataset, SplitStrategy
from modules.predictions.domain.value_objects import MarketId
from modules.predictions.ports.dataset_repository import DatasetRepositoryPort
from modules.predictions.ports.ml_model import MIN_TRAINING_SAMPLES
from modules.predictions.ports.repositories import FeatureMarketMappingRepositoryPort, MarketRepositoryPort

_REQUIRED_FEATURE_MISSING_RATE_THRESHOLD = 0.5


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class TrainingPreflightReport:
    market_key: str
    ready: bool
    checks: tuple[PreflightCheck, ...]

    def blocking(self) -> tuple[PreflightCheck, ...]:
        return tuple(c for c in self.checks if not c.passed)


@dataclass
class TrainingPreflightService:
    markets: MarketRepositoryPort
    mappings: FeatureMarketMappingRepositoryPort
    feature_definitions: FeatureDefinitionRepositoryPort
    dataset_builder: DatasetBuilder
    dataset_repo: DatasetRepositoryPort

    async def check(self, market_key: str, now: datetime) -> TrainingPreflightReport:
        checks: list[PreflightCheck] = []

        market = await self.markets.get_by_key(market_key)
        checks.append(
            PreflightCheck(
                "market_exists", market is not None,
                f"market '{market_key}' found in registry" if market else f"no market registered with key '{market_key}'",
            )
        )
        if market is None:
            return TrainingPreflightReport(market_key=market_key, ready=False, checks=tuple(checks))

        required_features, all_mapped_features = await self._required_and_all_features(market.id)
        checks.append(self._feature_manifest_declared(all_mapped_features))

        dataset = await self.dataset_builder.build(market.id, now)

        checks.append(self._sufficient_labeled_observations(dataset))
        checks.append(self._labels_valid(dataset))
        checks.append(self._temporal_reference_present(dataset))
        checks.append(self._temporal_split_valid(dataset))
        checks.append(await self._feature_versions_known(all_mapped_features))
        checks.append(self._training_inference_feature_parity(dataset, required_features))
        checks.append(self._required_feature_coverage_acceptable(dataset, required_features))
        checks.append(await self._intelligence_feature_leakage_safe(required_features))
        checks.append(await self._dataset_reproducible(market.id, now, dataset))
        checks.append(await self._dataset_provenance_persisted(market.id))

        ready = all(c.passed for c in checks)
        return TrainingPreflightReport(market_key=market_key, ready=ready, checks=tuple(checks))

    async def _required_and_all_features(self, market_id: MarketId) -> tuple[list[str], list[str]]:
        mappings = await self.mappings.list_by_market(market_id)
        required = sorted(m.feature_key for m in mappings if m.is_required)
        all_keys = sorted(m.feature_key for m in mappings)
        return required, all_keys

    def _feature_manifest_declared(self, all_mapped_features: list[str]) -> PreflightCheck:
        passed = len(all_mapped_features) > 0
        return PreflightCheck(
            "feature_manifest_declared", passed,
            f"{len(all_mapped_features)} feature(s) mapped to this market" if passed
            else "no feature_market_mappings exist for this market",
        )

    def _sufficient_labeled_observations(self, dataset: Dataset) -> PreflightCheck:
        n = len(dataset.samples)
        passed = n >= MIN_TRAINING_SAMPLES
        return PreflightCheck(
            "sufficient_labeled_observations", passed,
            f"{n} labeled sample(s) built (minimum {MIN_TRAINING_SAMPLES})",
        )

    def _labels_valid(self, dataset: Dataset) -> PreflightCheck:
        invalid = sum(1 for s in dataset.samples if not math.isfinite(s.label))
        passed = invalid == 0
        return PreflightCheck(
            "labels_valid", passed,
            "all recovered labels are finite" if passed else f"{invalid} sample(s) have a non-finite label",
        )

    def _temporal_reference_present(self, dataset: Dataset) -> PreflightCheck:
        missing = sum(1 for s in dataset.samples if s.reference_time is None)
        passed = missing == 0 and len(dataset.samples) > 0
        return PreflightCheck(
            "temporal_reference_present", passed,
            "every sample has a reference_time" if passed
            else f"{missing} of {len(dataset.samples)} sample(s) have no reference_time",
        )

    def _temporal_split_valid(self, dataset: Dataset) -> PreflightCheck:
        try:
            split_dataset(list(dataset.samples), SplitStrategy.TIME_SERIES_SPLIT)
        except (MissingTemporalReferenceError, InsufficientSamplesForSplitError) as exc:
            return PreflightCheck("temporal_split_valid", False, str(exc))
        return PreflightCheck(
            "temporal_split_valid", True,
            "TIME_SERIES_SPLIT dry run succeeded — chronological ordering intact (Milestone 18)",
        )

    async def _feature_versions_known(self, all_mapped_features: list[str]) -> PreflightCheck:
        unresolved = []
        for key in all_mapped_features:
            definition = await self.feature_definitions.get(FeatureKey(key))
            if definition is None or not definition.is_consumable():
                unresolved.append(key)
        passed = len(unresolved) == 0
        return PreflightCheck(
            "feature_versions_known", passed,
            "every mapped feature resolves to an ACTIVE FeatureDefinition" if passed
            else f"no ACTIVE FeatureDefinition for: {', '.join(unresolved)}",
        )

    def _training_inference_feature_parity(self, dataset: Dataset, required_features: list[str]) -> PreflightCheck:
        trained_keys = set(dataset.lineage.feature_keys)
        never_trained = [k for k in required_features if k not in trained_keys]
        passed = len(never_trained) == 0
        return PreflightCheck(
            "training_inference_feature_parity", passed,
            "every feature required at live inference has appeared in at least one training sample"
            if passed else
            "required at live inference but absent from every training sample: " + ", ".join(never_trained),
        )

    def _required_feature_coverage_acceptable(self, dataset: Dataset, required_features: list[str]) -> PreflightCheck:
        low_coverage: dict[str, float] = {}
        for key in required_features:
            missing_rate = dataset.statistics.missing_rate.get(key, 1.0)
            if missing_rate >= _REQUIRED_FEATURE_MISSING_RATE_THRESHOLD:
                low_coverage[key] = round((1.0 - missing_rate) * 100, 1)
        passed = len(low_coverage) == 0
        detail = (
            f"every required feature has < {_REQUIRED_FEATURE_MISSING_RATE_THRESHOLD:.0%} missing rate"
            if passed else
            "coverage below threshold: " + ", ".join(f"{k}={v}%" for k, v in low_coverage.items())
        )
        return PreflightCheck("required_feature_coverage_acceptable", passed, detail)

    async def _intelligence_feature_leakage_safe(self, required_features: list[str]) -> PreflightCheck:
        unsafe = []
        for key in required_features:
            definition = await self.feature_definitions.get(FeatureKey(key))
            if definition is not None and not definition.is_market_safe():
                unsafe.append(key)
        passed = len(unsafe) == 0
        return PreflightCheck(
            "intelligence_feature_leakage_safe", passed,
            "no required feature is classified POST_MATCH_ONLY" if passed
            else "POST_MATCH_ONLY (leakage-unsafe) required feature(s): " + ", ".join(unsafe),
        )

    async def _dataset_reproducible(self, market_id: MarketId, now: datetime, first: Dataset) -> PreflightCheck:
        second = await self.dataset_builder.build(market_id, now)
        passed = bool(first.content_hash) and first.content_hash == second.content_hash
        return PreflightCheck(
            "dataset_reproducible", passed,
            f"content_hash stable across two independent builds ({first.content_hash[:12]}...)" if passed
            else "content_hash differs across two independent builds of the same market",
        )

    async def _dataset_provenance_persisted(self, market_id: MarketId) -> PreflightCheck:
        persisted = await self.dataset_repo.list_by_market(market_id, limit=1)
        passed = len(persisted) > 0
        return PreflightCheck(
            "dataset_provenance_persisted", passed,
            f"{len(persisted)} durable Dataset version(s) on record for this market" if passed
            else "no Dataset has ever been durably persisted for this market (DatasetRepositoryPort "
                 "is in-memory-only by design — see M19 audit §13, ADR-008)",
        )
