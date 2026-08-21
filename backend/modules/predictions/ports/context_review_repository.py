"""Gemini Prediction Reasoning Engine — persistence port for `ContextualReview` (one row per
prediction, see `PredictionContextReviewModel`'s own docstring for why this overwrites rather
than appends).
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.contextual_reasoning import ContextualReview
from modules.predictions.domain.value_objects import PredictionId


class ContextReviewRepositoryPort(Protocol):
    async def record(self, prediction_id: PredictionId, review: ContextualReview) -> None: ...
    async def get_for_prediction(self, prediction_id: PredictionId) -> ContextualReview | None: ...
