"""Sports-Analyst Explainability — persistence port for `FootballExplanation` (one row per
prediction, see `FootballExplanationModel`'s own docstring for why this overwrites rather than
appends)."""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.football_explanation import FootballExplanation
from modules.predictions.domain.value_objects import PredictionId


class FootballExplanationRepositoryPort(Protocol):
    async def record(self, prediction_id: PredictionId, explanation: FootballExplanation) -> None: ...
    async def get_for_prediction(self, prediction_id: PredictionId) -> FootballExplanation | None: ...
