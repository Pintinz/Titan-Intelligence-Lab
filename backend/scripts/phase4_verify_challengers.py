"""Phase 4 §22 — load each of the 5 calibrated challenger models registered during the champion-
validation pass, verify the artifact loads, and run one real inference to confirm no
serialization/feature-mismatch issue. Read/verify only — never promotes."""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.predictions.domain.value_objects import ModelStatus, TargetType
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.infrastructure.ml.local_artifact_store import LocalFilesystemArtifactStore
from modules.predictions.infrastructure.persistence.models import ModelDefinitionModel

CHALLENGER_MODEL_KEYS = [
    "football.away_clean_sheet.gaussian_nb",
    "football.home_team_total_goals.mlp",
    "football.home_win_to_nil.gaussian_nb",
    "football.total_goals_over_under_1_5.mlp",
    "football.total_goals_over_under_4_5.logistic_regression",
]


async def main() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///dev.db",
        execution_options={"schema_translate_map": {"predictions": None}},
    )
    session = async_sessionmaker(engine, expire_on_commit=False)()

    result = await session.execute(
        select(ModelDefinitionModel).where(ModelDefinitionModel.status == ModelStatus.CHALLENGER.value)
    )
    challengers = result.scalars().all()
    print(f"Found {len(challengers)} real CHALLENGER rows in dev.db")

    loader = ModelLoaderService(artifact_store=LocalFilesystemArtifactStore())
    verified = 0
    for model in challengers:
        if not model.calibration_ref:
            continue
        try:
            adapter = await loader.load(
                model.id, model.framework, model.algorithm, TargetType.CLASSIFICATION, model.artifact_ref
            )
            probe_features = {k: 0.0 for k in adapter.feature_order}
            prediction = adapter.predict_one(probe_features)
            print(
                f"OK  {model.model_key} v{model.version} calibration={model.calibration_ref} "
                f"artifact={model.artifact_ref!r} feature_count={len(adapter.feature_order)} "
                f"probe_value={prediction.value!r} probe_probability={prediction.probability:.4f}"
            )
            verified += 1
        except Exception as exc:  # noqa: BLE001 — this script's whole job is to surface exactly this
            print(f"FAIL {model.model_key} v{model.version}: {type(exc).__name__}: {exc}")

    print(f"\n{verified}/{len([m for m in challengers if m.calibration_ref])} calibrated challengers verified")
    await session.close()
    await engine.dispose()


asyncio.run(main())
