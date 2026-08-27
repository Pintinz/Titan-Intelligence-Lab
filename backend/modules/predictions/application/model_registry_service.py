"""Model Registry — Champion/Challenger lifecycle (Milestone 9: "Exactly one CHAMPION per market
at a time", docs/prediction_markets.md "Champion-Challenger Requirement": no market's production
model changes without a documented Champion vs. Candidate offline benchmark recorded in
`predictions.experiments`).

This service enforces the *status* gate and the single-champion invariant only. Whether a
CHALLENGER *should* be promoted — the offline benchmark decision itself — is `Experiment`
territory (a separate concern, recorded before `promote_to_champion` is called); this service
does not re-derive that judgment, it only refuses to leave two CHAMPIONs standing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.predictions.domain.entities import ModelDefinition
from modules.predictions.domain.model_comparison import ComparisonVerdict
from modules.predictions.domain.value_objects import MarketId, ModelId, ModelStatus
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.ports.repositories import ModelComparisonRepositoryPort, ModelRepositoryPort


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — duplicated
    per-module rather than imported, matching the existing convention across this codebase."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


class ModelAlreadyRegisteredError(ValueError):
    pass


class ModelNotFoundError(KeyError):
    pass


class InvalidModelLifecycleTransitionError(ValueError):
    pass


class InvalidDeploymentModeError(ValueError):
    pass


class TrainingIntegrityError(ValueError):
    """Raised by `promote_to_champion` for a model whose `provenance_status` is
    `PROVENANCE_COMPROMISED` (forensic audit §10) — a real, checked finding that this model's
    training data has a confirmed point-in-time violation, not merely an unreviewed one. Promoting
    it anyway would silently reintroduce the exact leakage Critical Fix #1 closed at the data
    layer. The only way past this is a genuine clean retrain that registers a new CANDIDATE/
    CHALLENGER — `scripts/assess_training_integrity.py` never marks a freshly-registered model
    compromised without re-running the check."""


class PromotionPolicyViolationError(ValueError):
    """Forensic audit §11/§12 "Champion Promotion Safety": raised by `promote_to_champion` when a
    market that already has a live Champion (i.e. this is not the market's first-ever promotion —
    nothing to compare a bootstrap Candidate against) lacks the one thing that's supposed to make
    promotion a decision rather than a formality: a real, current, favorable comparison against
    that Champion. `reason_code` is one of:

    - "COMPARISON_MISSING" — no `ChallengerEvaluation` was ever recorded for this exact model.
    - "COMPARISON_STALE" — one exists, but it's older than `ModelRegistryService.max_comparison_age`
      (the market's data, or the Champion itself, may have moved on since it ran).
    - "CANDIDATE_NOT_BETTER" — one exists and is fresh, but its verdict isn't CHALLENGER_BETTER
      (CHAMPION_BETTER candidates are already auto-retired by the orchestrator before this would
      ever fire — this is defense-in-depth against a comparison recorded by some other path).
    - "ARTIFACT_INTEGRITY_FAILURE" — the candidate's own artifact fails to load (see
      `ModelLoaderService.load`/`ArtifactIntegrityError`) — promoting a model whose own artifact
      can't be served would just relabel today's silent-fallback incident as tomorrow's."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


_VALID_DEPLOYMENT_MODES = {"shadow", "canary", "live", None}


@dataclass
class ModelRegistryService:
    models: ModelRepositoryPort
    # Section 30 audit fix (2026-08-23): `ModelLoaderService.invalidate()` has existed since
    # Milestone 9.1 with a docstring claiming it's "called on rollback/re-promotion" — but nothing
    # ever actually called it from here, leaving that claim documented and unimplemented. Optional
    # and defaults to None so every existing caller/test that doesn't wire a loader is unaffected;
    # when wired, promote_to_champion/rollback evict the loader's cache for every model whose
    # CHAMPION/RETIRED status just changed, so a stale cached artifact can never keep serving
    # under a market's new champion.
    model_loader: ModelLoaderService | None = None
    # Forensic audit §11/§12 — optional and defaults to `None` so every existing caller/test that
    # doesn't wire it (backfill/seeding scripts registering placeholder anchors, unit tests
    # exercising the lifecycle gate in isolation) keeps working exactly as before; wired in
    # production (`composition.py`'s `build_model_registry_service`) is what actually makes the
    # comparison-requirement gate below real rather than a documented-but-optional courtesy.
    comparisons: ModelComparisonRepositoryPort | None = None
    max_comparison_age: timedelta = timedelta(days=7)

    async def register(
        self,
        market_id: MarketId,
        model_key: str,
        version: int,
        algorithm: str,
        training_dataset_ref: str | None = None,
        calibration_ref: str | None = None,
        now: datetime | None = None,
        framework: str | None = None,
        dataset_version: int | None = None,
        feature_versions: dict | None = None,
        training_run_ref: str | None = None,
        calibration_report_ref: str | None = None,
        feature_importance_ref: str | None = None,
        artifact_ref: str | None = None,
        trained_at: datetime | None = None,
        artifact_checksum: str | None = None,
    ) -> ModelDefinition:
        if await self.models.get_by_key_version(model_key, version) is not None:
            raise ModelAlreadyRegisteredError(f"model '{model_key}' v{version} is already registered")

        model = ModelDefinition(
            id=ModelId(uuid4()),
            market_id=market_id,
            model_key=model_key,
            version=version,
            algorithm=algorithm,
            status=ModelStatus.CANDIDATE,
            training_dataset_ref=training_dataset_ref,
            calibration_ref=calibration_ref,
            created_at=now,
            framework=framework,
            dataset_version=dataset_version,
            feature_versions=feature_versions or {},
            training_run_ref=training_run_ref,
            calibration_report_ref=calibration_report_ref,
            feature_importance_ref=feature_importance_ref,
            artifact_ref=artifact_ref,
            trained_at=trained_at,
            artifact_checksum=artifact_checksum,
        )
        return await self.models.upsert(model)

    async def set_deployment_mode(self, model_id: ModelId, mode: str | None) -> ModelDefinition:
        """Milestone 9.1 "Deployment Status" — shadow deployment/A-B testing/canary rollout are
        finer-grained than the CANDIDATE/CHALLENGER/CHAMPION/RETIRED lifecycle `status` already
        enforces; this tracks *how* a model (typically a CHALLENGER) is currently being exercised,
        independent of that lifecycle gate."""
        if mode not in _VALID_DEPLOYMENT_MODES:
            raise InvalidDeploymentModeError(f"'{mode}' is not one of {sorted(m for m in _VALID_DEPLOYMENT_MODES if m)}")
        model = await self._require(model_id)
        model.deployment_mode = mode
        return await self.models.upsert(model)

    async def promote_to_challenger(self, model_id: ModelId) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is not ModelStatus.CANDIDATE:
            raise InvalidModelLifecycleTransitionError(
                f"cannot promote model '{model.model_key}' v{model.version} to CHALLENGER "
                f"from {model.status.value} — must be CANDIDATE"
            )
        model.status = ModelStatus.CHALLENGER
        return await self.models.upsert(model)

    async def promote_to_champion(self, model_id: ModelId, approved_by: str, now: datetime) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is not ModelStatus.CHALLENGER:
            raise InvalidModelLifecycleTransitionError(
                f"cannot promote model '{model.model_key}' v{model.version} to CHAMPION "
                f"from {model.status.value} — must be CHALLENGER"
            )
        if model.is_training_compromised():
            raise TrainingIntegrityError(
                f"cannot promote model '{model.model_key}' v{model.version} to CHAMPION — its "
                f"provenance_status is PROVENANCE_COMPROMISED (confirmed point-in-time leakage in "
                f"its training data, see scripts/assess_training_integrity.py). Retrain from clean "
                f"data and promote the resulting CANDIDATE/CHALLENGER instead."
            )

        current_champion = await self.models.get_champion(model.market_id)

        # Forensic audit §11/§12 — the comparison-requirement gate. Only applies once this market
        # already has a live Champion: a market's very first-ever promotion (the bootstrap case
        # `ScheduledRetrainingOrchestrator` handles automatically) has nothing to compare against
        # by definition, and that gap is a real, structural absence of evidence, not a candidate
        # that failed a comparison — so it stays exempt, exactly like the noise-band INCONCLUSIVE
        # verdict already gets deliberately narrowed by `_decide()` returning ("none" reason) for
        # that same case at the evaluation layer.
        if current_champion is not None and current_champion.id != model.id and self.comparisons is not None:
            await self._require_favorable_comparison(model, now)

        # NOTE (scoped out, not overlooked): the brief also asks for an "artifact integrity fails"
        # promotion-time check — actually loading the candidate's artifact via `ModelLoaderService`
        # before promoting, not just at first serve. `ModelLoaderService.load()` needs the market's
        # `TargetType` to construct the right adapter shell, and this service only holds a
        # `ModelRepositoryPort` — no market lookup — so doing this properly means adding a
        # `markets` dependency here too, a real (if small) design change deferred to its own pass
        # rather than done half-right with a guessed `TargetType`. The checksum this artifact was
        # registered with is NOT unenforced in the meantime: `PredictionEngine._resolve_predictor`
        # already verifies it (Phase 2, `ArtifactIntegrityError`) on the very first prediction this
        # Champion serves, and falls back safely with `fallback_reason=ARTIFACT_INTEGRITY_MISMATCH`
        # rather than silently serving a tampered/corrupt model — so a bad artifact cannot reach a
        # real prediction even though promotion itself doesn't pre-empt it yet.

        if current_champion is not None and current_champion.id != model.id:
            current_champion.status = ModelStatus.RETIRED
            current_champion.retired_at = now
            await self.models.upsert(current_champion)
            if self.model_loader is not None:
                self.model_loader.invalidate(current_champion.id)

        model.status = ModelStatus.CHAMPION
        model.approved_by = approved_by
        model.approved_at = now
        model.promoted_at = now
        saved = await self.models.upsert(model)
        if self.model_loader is not None:
            self.model_loader.invalidate(saved.id)
        return saved

    async def _require_favorable_comparison(self, candidate: ModelDefinition, now: datetime) -> None:
        """The one policy both the manual `POST /champion/{id}/promote` endpoint and the automatic
        retraining sweep now go through — neither calls `ChallengerEvaluationService`/inspects a
        `ChallengerEvaluation` itself, so there is exactly one place this rule can be bypassed by
        a caller forgetting to check it: here. `status == CHALLENGER` was previously treated as
        sufficient evidence on its own (forensic audit finding); it no longer is."""
        # Phase 7 audit fix (2026-08-25): a direct `(market_id, challenger_model_id)` lookup, never
        # "the market's most recent N comparisons, client-filtered" — the latter silently produced
        # a false COMPARISON_MISSING once 50+ *other* comparisons had been recorded for the same
        # market since this candidate's own (a real risk for a fast-retraining market with a
        # delayed human promotion decision).
        comparison = await self.comparisons.get_for_challenger(candidate.market_id, candidate.id)

        if comparison is None:
            raise PromotionPolicyViolationError(
                "COMPARISON_MISSING",
                f"cannot promote model '{candidate.model_key}' v{candidate.version} to CHAMPION — "
                f"no comparison against the current Champion has ever been recorded for it. Run "
                f"the retraining/comparison pipeline (or a manual comparison) before promoting.",
            )

        age = now - _ensure_aware(comparison.evaluated_at, now)
        if age > self.max_comparison_age:
            raise PromotionPolicyViolationError(
                "COMPARISON_STALE",
                f"cannot promote model '{candidate.model_key}' v{candidate.version} to CHAMPION — "
                f"its comparison against the Champion ran {age.days}d ago, older than the "
                f"{self.max_comparison_age.days}d freshness window. Re-run the comparison before "
                f"promoting; the market's data or the current Champion may have changed since.",
            )

        if comparison.verdict is not ComparisonVerdict.CHALLENGER_BETTER:
            raise PromotionPolicyViolationError(
                "CANDIDATE_NOT_BETTER",
                f"cannot promote model '{candidate.model_key}' v{candidate.version} to CHAMPION — "
                f"its comparison against the Champion returned {comparison.verdict.value}, not "
                f"challenger_better (decisive metric: {comparison.decisive_metric}).",
            )

    async def rollback(self, market_id: MarketId, now: datetime) -> ModelDefinition:
        """Retires the current champion and reinstates the most recently retired model as
        champion — the Admin Action "Rollback" (Milestone 9 Part 6)."""
        current_champion = await self.models.get_champion(market_id)
        if current_champion is None:
            raise ModelNotFoundError(f"no champion set for market {market_id}")

        retired = await self.models.list_by_status(market_id, ModelStatus.RETIRED)
        if not retired:
            raise ModelNotFoundError(f"no retired model to roll back to for market {market_id}")
        previous = max(retired, key=lambda m: m.retired_at)

        current_champion.status = ModelStatus.RETIRED
        current_champion.retired_at = now
        await self.models.upsert(current_champion)
        if self.model_loader is not None:
            self.model_loader.invalidate(current_champion.id)

        previous.status = ModelStatus.CHAMPION
        previous.promoted_at = now
        previous.retired_at = None
        saved = await self.models.upsert(previous)
        if self.model_loader is not None:
            self.model_loader.invalidate(saved.id)
        return saved

    async def retire(self, model_id: ModelId, now: datetime) -> ModelDefinition:
        model = await self._require(model_id)
        if model.status is ModelStatus.RETIRED:
            raise InvalidModelLifecycleTransitionError(f"model '{model.model_key}' v{model.version} already retired")
        model.status = ModelStatus.RETIRED
        model.retired_at = now
        return await self.models.upsert(model)

    async def _require(self, model_id: ModelId) -> ModelDefinition:
        model = await self.models.get(model_id)
        if model is None:
            raise ModelNotFoundError(str(model_id))
        return model
