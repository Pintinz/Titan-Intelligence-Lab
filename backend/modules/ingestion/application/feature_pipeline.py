"""Feature Pipeline Foundation (docs/roadmap.md Milestone 5).

Implements the architecture only:

    Raw Provider Data -> Normalized Data -> Validated Data -> Clean Data
        -> Feature Calculators -> Feature Store -> AI Models

as a composable stage sequence with zero registered calculators. Sport-specific engineered
features are explicitly out of scope this milestone ("Do NOT implement sport-specific
engineered features yet. Only implement the pipeline architecture.") — Milestone 6 registers
the first real ``FeatureCalculatorPort`` implementations against this same pipeline.

``normalize``/``validate``/``clean`` are injected per call rather than being pipeline state,
because what a "clean record" looks like is entity-specific (a clean Team record and a clean
Fixture record share nothing) — the pipeline's job is sequencing those steps and running
calculators over the result, not defining what cleaning means for any one entity.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from modules.ingestion.application.data_validation_engine import ValidationResult
from modules.ingestion.ports.feature_pipeline import FeatureCalculatorPort


@dataclass(frozen=True)
class PipelineResult:
    stage_reached: str  # "normalized" | "validated" | "cleaned" | "calculated"
    validation: ValidationResult | None
    clean_record: dict | None
    computed_features: tuple[tuple[str, float | int | str | bool], ...] = field(default_factory=tuple)


@dataclass
class FeaturePipeline:
    calculators: list[FeatureCalculatorPort] = field(default_factory=list)

    def register_calculator(self, calculator: FeatureCalculatorPort) -> None:
        if any(c.feature_key == calculator.feature_key for c in self.calculators):
            raise ValueError(f"a calculator for '{calculator.feature_key}' is already registered")
        self.calculators.append(calculator)

    async def run(
        self,
        raw: dict,
        now: datetime,
        *,
        normalize: Callable[[dict], dict],
        validate: Callable[[dict], ValidationResult],
        clean: Callable[[dict], dict],
    ) -> PipelineResult:
        normalized = normalize(raw)
        validation = validate(normalized)
        if not validation.is_valid:
            return PipelineResult(stage_reached="validated", validation=validation, clean_record=None)

        clean_record = clean(normalized)
        computed = []
        for calculator in self.calculators:
            value = await calculator.compute(clean_record, now)
            if value is not None:
                computed.append((calculator.feature_key, value))

        return PipelineResult(
            stage_reached="calculated" if self.calculators else "cleaned",
            validation=validation, clean_record=clean_record, computed_features=tuple(computed),
        )
