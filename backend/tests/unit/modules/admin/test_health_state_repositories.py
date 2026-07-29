import uuid
from datetime import datetime, timedelta, timezone

import pytest

from modules.admin.domain.entities import (
    ProviderDefinition,
    ProviderHealthCheck,
    ProviderHealthState,
    ProviderIncident,
)
from modules.admin.domain.value_objects import (
    HealthStatus,
    IncidentId,
    IncidentSeverity,
    ProviderCategory,
    ProviderId,
)
from modules.admin.infrastructure.persistence.repositories import (
    SqlAlchemyHealthRepository,
    SqlAlchemyHealthStateRepository,
    SqlAlchemyIncidentRepository,
    SqlAlchemyProviderRepository,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


async def _seed_provider(sqlite_session) -> ProviderId:
    repo = SqlAlchemyProviderRepository(session=sqlite_session)
    provider = ProviderDefinition(
        id=ProviderId(uuid.uuid4()), key="api_football", name="API-Football", category=ProviderCategory.SPORTS_DATA
    )
    await repo.upsert(provider)
    return provider.id


@pytest.mark.asyncio
async def test_health_check_list_since_filters_by_time(sqlite_session):
    provider_id = await _seed_provider(sqlite_session)
    repo = SqlAlchemyHealthRepository(session=sqlite_session)

    await repo.record(ProviderHealthCheck(provider_id=provider_id, checked_at=T0, success=True))
    await repo.record(
        ProviderHealthCheck(provider_id=provider_id, checked_at=T0 + timedelta(hours=2), success=False)
    )
    await sqlite_session.commit()

    recent = await repo.list_since(provider_id, T0 + timedelta(hours=1))

    assert len(recent) == 1
    assert recent[0].success is False


@pytest.mark.asyncio
async def test_health_state_round_trip(sqlite_session):
    provider_id = await _seed_provider(sqlite_session)
    repo = SqlAlchemyHealthStateRepository(session=sqlite_session)

    state = ProviderHealthState(
        provider_id=provider_id,
        status=HealthStatus.DEGRADED,
        consecutive_failures=3,
        consecutive_successes=0,
        last_check_at=T0,
        last_failure_at=T0,
    )
    await repo.upsert(state)
    await sqlite_session.commit()

    fetched = await repo.get(provider_id)

    assert fetched is not None
    assert fetched.status is HealthStatus.DEGRADED
    assert fetched.consecutive_failures == 3


@pytest.mark.asyncio
async def test_health_state_update_in_place(sqlite_session):
    provider_id = await _seed_provider(sqlite_session)
    repo = SqlAlchemyHealthStateRepository(session=sqlite_session)

    await repo.upsert(ProviderHealthState(provider_id=provider_id, status=HealthStatus.HEALTHY))
    await sqlite_session.commit()

    await repo.upsert(ProviderHealthState(provider_id=provider_id, status=HealthStatus.DOWN, consecutive_failures=5))
    await sqlite_session.commit()

    fetched = await repo.get(provider_id)
    assert fetched.status is HealthStatus.DOWN
    assert fetched.consecutive_failures == 5


@pytest.mark.asyncio
async def test_incident_round_trip_and_open_filter(sqlite_session):
    provider_id = await _seed_provider(sqlite_session)
    repo = SqlAlchemyIncidentRepository(session=sqlite_session)

    open_incident = ProviderIncident(
        id=IncidentId(uuid.uuid4()),
        provider_id=provider_id,
        severity=IncidentSeverity.WARNING,
        opened_at=T0,
        trigger="2 consecutive failures",
    )
    resolved_incident = ProviderIncident(
        id=IncidentId(uuid.uuid4()),
        provider_id=provider_id,
        severity=IncidentSeverity.CRITICAL,
        opened_at=T0 - timedelta(days=1),
        trigger="5 consecutive failures",
        resolved_at=T0 - timedelta(hours=1),
    )
    await repo.upsert(open_incident)
    await repo.upsert(resolved_incident)
    await sqlite_session.commit()

    all_incidents = await repo.list_by_provider(provider_id)
    open_only = await repo.list_open(provider_id)
    fetched = await repo.get(open_incident.id)

    assert len(all_incidents) == 2
    assert len(open_only) == 1
    assert open_only[0].id == open_incident.id
    assert fetched is not None and fetched.trigger == "2 consecutive failures"


@pytest.mark.asyncio
async def test_incident_escalation_persists_severity_change(sqlite_session):
    provider_id = await _seed_provider(sqlite_session)
    repo = SqlAlchemyIncidentRepository(session=sqlite_session)

    incident = ProviderIncident(
        id=IncidentId(uuid.uuid4()),
        provider_id=provider_id,
        severity=IncidentSeverity.WARNING,
        opened_at=T0,
        trigger="2 consecutive failures",
    )
    await repo.upsert(incident)
    await sqlite_session.commit()

    incident.severity = IncidentSeverity.CRITICAL
    await repo.upsert(incident)
    await sqlite_session.commit()

    fetched = await repo.get(incident.id)
    assert fetched.severity is IncidentSeverity.CRITICAL
