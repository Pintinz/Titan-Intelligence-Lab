"""Calibration Parameters repository port — the durable store behind `PlattScalingCalibrator`.
Concrete implementation lives in modules/predictions/infrastructure/persistence.
"""

from __future__ import annotations

from typing import Protocol

from modules.predictions.domain.calibration import PlattCalibrationParameters
from modules.predictions.domain.value_objects import ModelId


class CalibrationParametersRepositoryPort(Protocol):
    async def get(self, model_id: ModelId) -> PlattCalibrationParameters | None: ...
    async def upsert(self, params: PlattCalibrationParameters) -> PlattCalibrationParameters: ...
