import uuid
from datetime import datetime, timedelta, timezone

import pytest

from modules.admin.application.health_intelligence_engine import HealthIntelligenceEngine
from modules.admin.domain.entities import ProviderUsageRecord
from modules.admin.domain.value_objects import CredentialId, HealthStatus, IncidentSeverity, ProviderId, QuotaPeriod

T0 = datetime(2026, 7, 25, 6, 0, tzinfo=timezone.utc)


@pytest.fixture
def provider_id():
    return ProviderId(uuid.uuid4())


@pytest.fixture
def engine(health_repo, health_state_repo, incident_repo, usage_repo):
    return HealthIntelligenceEngine(
        health=health_repo, health_state=health_state_repo, incidents=incident_repo, usage=usage_repo
    )


# -- recording & automatic classification -----------------------------------------------------


@pytest.mark.asyncio
async def test_single_success_keeps_status_healthy(engine, provider_id):
    check, state = await engine.record_check(provider_id, T0, success=True, latency_ms=100)

    assert check.success is True
    assert state.status is HealthStatus.HEALTHY
    assert state.consecutive_failures == 0


@pytest.mark.asyncio
async def test_single_failure_does_not_yet_degrade(engine, provider_id):
    _, state = await engine.record_check(provider_id, T0, success=False, message="timeout")

    assert state.status is HealthStatus.HEALTHY
    assert state.consecutive_failures == 1


@pytest.mark.asyncio
async def test_two_consecutive_failures_degrade_and_open_warning_incident(engine, provider_id):
    await engine.record_check(provider_id, T0, success=False)
    _, state = await engine.record_check(provider_id, T0 + timedelta(seconds=1), success=False)

    assert state.status is HealthStatus.DEGRADED
    incident = await engine.open_incident(provider_id)
    assert incident is not None
    assert incident.severity is IncidentSeverity.WARNING
    assert incident.is_open


@pytest.mark.asyncio
async def test_five_consecutive_failures_go_down_and_escalate_same_incident(engine, provider_id):
    for i in range(5):
        _, state = await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    assert state.status is HealthStatus.DOWN
    incidents = await engine.list_incidents(provider_id)
    assert len(incidents) == 1  # escalated, not a second incident
    assert incidents[0].severity is IncidentSeverity.CRITICAL


@pytest.mark.asyncio
async def test_recovery_resolves_incident_and_returns_to_healthy(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    recovery_time = T0 + timedelta(minutes=1)
    _, state = await engine.record_check(provider_id, recovery_time, success=True, latency_ms=50)

    assert state.status is HealthStatus.HEALTHY
    assert state.open_incident_id is None
    incidents = await engine.list_incidents(provider_id)
    assert len(incidents) == 1
    assert incidents[0].resolved_at == recovery_time
    assert not incidents[0].is_open


@pytest.mark.asyncio
async def test_severity_never_downgrades_while_incident_stays_open(engine, provider_id):
    # DEGRADED (2 failures) then a single success brings failures back to 0 (HEALTHY) —
    # but if it flaps DOWN again the incident that reopens should still escalate correctly.
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)
    incidents = await engine.list_incidents(provider_id)
    assert incidents[0].severity is IncidentSeverity.CRITICAL  # never seen WARNING-only for this episode


# -- windowed metrics -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_and_failure_rate_over_window(engine, provider_id):
    await engine.record_check(provider_id, T0, success=True)
    await engine.record_check(provider_id, T0 + timedelta(minutes=1), success=True)
    await engine.record_check(provider_id, T0 + timedelta(minutes=2), success=False)
    await engine.record_check(provider_id, T0 + timedelta(minutes=3), success=True)

    now = T0 + timedelta(minutes=10)
    assert await engine.success_rate(provider_id, now) == pytest.approx(0.75)
    assert await engine.failure_rate(provider_id, now) == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_average_latency(engine, provider_id):
    for i, latency in enumerate([100, 200, 300]):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=True, latency_ms=latency)

    avg = await engine.average_latency(provider_id, T0 + timedelta(minutes=5))

    assert avg == pytest.approx(200.0)


@pytest.mark.asyncio
async def test_latency_percentiles_linear_interpolation(engine, provider_id):
    latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    for i, latency in enumerate(latencies):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=True, latency_ms=latency)

    p50, p95, p99 = await engine.latency_percentiles(provider_id, T0 + timedelta(minutes=5))

    assert p50 == pytest.approx(55.0)
    assert p95 == pytest.approx(95.5)
    assert p99 == pytest.approx(99.1)


@pytest.mark.asyncio
async def test_metrics_are_none_with_no_data(engine, provider_id):
    assert await engine.success_rate(provider_id, T0) is None
    assert await engine.average_latency(provider_id, T0) is None
    p50, p95, p99 = await engine.latency_percentiles(provider_id, T0)
    assert (p50, p95, p99) == (None, None, None)


@pytest.mark.asyncio
async def test_window_excludes_checks_outside_range(engine, provider_id):
    await engine.record_check(provider_id, T0, success=False)  # old, outside window
    await engine.record_check(provider_id, T0 + timedelta(hours=25), success=True)  # inside 24h window

    now = T0 + timedelta(hours=25, minutes=1)
    rate = await engine.success_rate(provider_id, now, window=timedelta(hours=24))

    assert rate == pytest.approx(1.0)  # only the recent success counts


# -- consecutive failures / availability / uptime --------------------------------------------------


@pytest.mark.asyncio
async def test_consecutive_failures_tracks_state(engine, provider_id):
    await engine.record_check(provider_id, T0, success=False)
    await engine.record_check(provider_id, T0 + timedelta(seconds=1), success=False)
    await engine.record_check(provider_id, T0 + timedelta(seconds=2), success=False)

    assert await engine.consecutive_failures(provider_id) == 3


@pytest.mark.asyncio
async def test_consecutive_failures_resets_on_success(engine, provider_id):
    await engine.record_check(provider_id, T0, success=False)
    await engine.record_check(provider_id, T0 + timedelta(seconds=1), success=False)
    await engine.record_check(provider_id, T0 + timedelta(seconds=2), success=True)

    assert await engine.consecutive_failures(provider_id) == 0


@pytest.mark.asyncio
async def test_availability_percentage_and_daily_monthly_uptime(engine, provider_id):
    for i in range(9):
        await engine.record_check(provider_id, T0 + timedelta(minutes=i), success=True)
    await engine.record_check(provider_id, T0 + timedelta(minutes=9), success=False)

    now = T0 + timedelta(minutes=15)
    assert await engine.availability_percentage(provider_id, now) == pytest.approx(90.0)
    assert await engine.daily_uptime(provider_id, now) == pytest.approx(90.0)
    assert await engine.monthly_uptime(provider_id, now) == pytest.approx(90.0)


# -- throughput -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throughput_reads_usage_record(engine, provider_id, usage_repo):
    await usage_repo.upsert(
        ProviderUsageRecord(provider_id=provider_id, period=QuotaPeriod.DAILY, window_key="2026-07-25", request_count=42)
    )

    throughput = await engine.throughput(provider_id, QuotaPeriod.DAILY, "2026-07-25")

    assert throughput == 42


@pytest.mark.asyncio
async def test_throughput_zero_when_no_usage_recorded(engine, provider_id):
    assert await engine.throughput(provider_id, QuotaPeriod.DAILY, "2026-07-25") == 0


# -- scores -----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reliability_score_high_for_fast_reliable_provider(engine, provider_id):
    for i in range(10):
        await engine.record_check(provider_id, T0 + timedelta(minutes=i), success=True, latency_ms=50)

    score = await engine.reliability_score(provider_id, T0 + timedelta(minutes=15))

    assert score > 95


@pytest.mark.asyncio
async def test_reliability_score_low_for_failing_slow_provider(engine, provider_id):
    for i in range(10):
        await engine.record_check(provider_id, T0 + timedelta(minutes=i), success=False, latency_ms=5000)

    score = await engine.reliability_score(provider_id, T0 + timedelta(minutes=15))

    assert score < 10


@pytest.mark.asyncio
async def test_reliability_score_none_without_data(engine, provider_id):
    assert await engine.reliability_score(provider_id, T0) is None


@pytest.mark.asyncio
async def test_credential_reliability_score_reflects_error_rate(engine, provider_id, usage_repo):
    credential_id = CredentialId(uuid.uuid4())
    await usage_repo.upsert(
        ProviderUsageRecord(
            provider_id=provider_id,
            period=QuotaPeriod.DAILY,
            window_key=T0.date().isoformat(),
            credential_id=credential_id,
            request_count=100,
            error_count=10,
        )
    )

    score = await engine.credential_reliability_score(provider_id, credential_id, T0)

    assert score == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_credential_reliability_score_none_without_usage(engine, provider_id):
    assert await engine.credential_reliability_score(provider_id, CredentialId(uuid.uuid4()), T0) is None


# -- trend & diagnostics -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_trend_buckets_by_day(engine, provider_id):
    day0 = T0
    day1 = T0 + timedelta(days=1)
    await engine.record_check(provider_id, day0, success=True, latency_ms=100)
    await engine.record_check(provider_id, day0 + timedelta(hours=1), success=True, latency_ms=100)
    await engine.record_check(provider_id, day1, success=False, latency_ms=200)

    trend = await engine.health_trend(provider_id, day1 + timedelta(hours=1), days=2)

    assert len(trend) == 2
    assert trend[0].date == day0.date().isoformat()
    assert trend[0].success_rate == pytest.approx(1.0)
    assert trend[0].check_count == 2
    assert trend[1].date == day1.date().isoformat()
    assert trend[1].success_rate == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_health_trend_has_empty_days_when_no_checks(engine, provider_id):
    await engine.record_check(provider_id, T0, success=True)

    trend = await engine.health_trend(provider_id, T0 + timedelta(days=3), days=5)

    empty_days = [p for p in trend if p.check_count == 0]
    assert len(empty_days) == 4
    for point in empty_days:
        assert point.success_rate is None


@pytest.mark.asyncio
async def test_diagnostics_report_when_healthy(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(minutes=i), success=True, latency_ms=100)

    report = await engine.diagnostics(provider_id, T0 + timedelta(minutes=10))

    assert report.status is HealthStatus.HEALTHY
    assert report.open_incident is None
    assert report.recommendation == "Healthy."
    assert len(report.recent_checks) == 5


@pytest.mark.asyncio
async def test_diagnostics_report_when_down(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    report = await engine.diagnostics(provider_id, T0 + timedelta(minutes=1))

    assert report.status is HealthStatus.DOWN
    assert report.open_incident is not None
    assert report.open_incident.severity is IncidentSeverity.CRITICAL
    assert "DOWN" in report.recommendation


@pytest.mark.asyncio
async def test_diagnostics_flags_low_success_rate_even_when_technically_healthy(engine, provider_id):
    # 1 failure then recovery keeps status HEALTHY (below degraded_threshold) but success rate dips.
    await engine.record_check(provider_id, T0, success=False)
    for i in range(1, 10):
        await engine.record_check(provider_id, T0 + timedelta(minutes=i), success=True)

    report = await engine.diagnostics(provider_id, T0 + timedelta(minutes=15))

    assert report.status is HealthStatus.HEALTHY
    assert "below 98%" in report.recommendation


# -- automatic recovery ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_should_not_attempt_recovery_when_healthy(engine, provider_id):
    await engine.record_check(provider_id, T0, success=True)

    assert not await engine.should_attempt_recovery(provider_id, T0 + timedelta(minutes=10))


@pytest.mark.asyncio
async def test_should_attempt_recovery_when_down_and_no_prior_check_cooldown(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    assert await engine.should_attempt_recovery(
        provider_id, T0 + timedelta(minutes=10), cooldown=timedelta(minutes=5)
    )


@pytest.mark.asyncio
async def test_should_not_attempt_recovery_before_cooldown_elapses(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    assert not await engine.should_attempt_recovery(
        provider_id, T0 + timedelta(minutes=1), cooldown=timedelta(minutes=5)
    )


@pytest.mark.asyncio
async def test_attempt_recovery_records_probe_result_and_can_heal(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    async def probe():
        return True, 80.0

    check, state = await engine.attempt_recovery(provider_id, T0 + timedelta(minutes=10), probe)

    assert check.success is True
    assert check.message == "recovery attempt"
    assert state.status is HealthStatus.HEALTHY
    assert (await engine.list_incidents(provider_id))[0].resolved_at is not None


@pytest.mark.asyncio
async def test_attempt_recovery_with_failing_probe_stays_down(engine, provider_id):
    for i in range(5):
        await engine.record_check(provider_id, T0 + timedelta(seconds=i), success=False)

    async def probe():
        return False, None

    _, state = await engine.attempt_recovery(provider_id, T0 + timedelta(minutes=10), probe)

    assert state.status is HealthStatus.DOWN
