import uuid
from datetime import datetime, timezone

import pytest

from modules.admin.domain.entities import FeatureFlag
from modules.admin.domain.value_objects import FlagId
from modules.admin.infrastructure.persistence.repositories import SqlAlchemyFeatureFlagRepository

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_feature_flag_round_trip(sqlite_session):
    repo = SqlAlchemyFeatureFlagRepository(session=sqlite_session)
    flag = FeatureFlag(
        id=FlagId(uuid.uuid4()),
        key="table_tennis_predictions",
        name="Table Tennis Predictions",
        description="Gate table tennis prediction markets from GA",
        enabled=True,
        rollout_percentage=25,
        updated_at=T0,
    )

    await repo.upsert(flag)
    await sqlite_session.commit()

    fetched = await repo.get(flag.id)
    by_key = await repo.get_by_key("table_tennis_predictions")

    assert fetched is not None
    assert fetched.enabled is True
    assert fetched.rollout_percentage == 25
    assert by_key is not None and by_key.id == flag.id


@pytest.mark.asyncio
async def test_feature_flag_list_all(sqlite_session):
    repo = SqlAlchemyFeatureFlagRepository(session=sqlite_session)
    await repo.upsert(FeatureFlag(id=FlagId(uuid.uuid4()), key="a", name="A", description="d"))
    await repo.upsert(FeatureFlag(id=FlagId(uuid.uuid4()), key="b", name="B", description="d"))
    await sqlite_session.commit()

    flags = await repo.list_all()

    assert {f.key for f in flags} == {"a", "b"}


@pytest.mark.asyncio
async def test_feature_flag_update_in_place(sqlite_session):
    repo = SqlAlchemyFeatureFlagRepository(session=sqlite_session)
    flag = FeatureFlag(id=FlagId(uuid.uuid4()), key="a", name="A", description="d", enabled=False)
    await repo.upsert(flag)
    await sqlite_session.commit()

    flag.enabled = True
    flag.rollout_percentage = 50
    await repo.upsert(flag)
    await sqlite_session.commit()

    fetched = await repo.get(flag.id)
    assert fetched.enabled is True
    assert fetched.rollout_percentage == 50
