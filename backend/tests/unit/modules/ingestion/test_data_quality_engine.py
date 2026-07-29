from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.ingestion.application.data_quality_engine import IngestionQualityEngine
from modules.ingestion.domain.entities import SyncRun
from modules.ingestion.domain.value_objects import EntityKind, SyncRunId, SyncStatus, SyncTrigger

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def _run(status, started_at, finished_at=None) -> SyncRun:
    return SyncRun(
        id=SyncRunId(uuid4()), sport_code="football", entity_kind=EntityKind.TEAM, scope_key="39",
        trigger=SyncTrigger.SCHEDULED, status=status, started_at=started_at, finished_at=finished_at,
    )


@pytest.fixture
def engine(sync_run_repo, quality_report_repo, provider_reliability_port):
    return IngestionQualityEngine(
        sync_runs=sync_run_repo, reports=quality_report_repo, provider_quality_port=provider_reliability_port
    )


@pytest.mark.asyncio
async def test_perfect_batch_yields_high_scores(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, missing_count=0, invalid_count=0,
        relationship_issue_count=0, duplicate_count=0,
    )

    assert report.completeness_pct == pytest.approx(100.0)
    assert report.consistency_pct == pytest.approx(100.0)
    assert report.validity_pct == pytest.approx(100.0)
    assert report.accuracy_pct == report.validity_pct
    assert report.freshness_score == pytest.approx(100.0)
    assert report.reliability_score == pytest.approx(100.0)
    assert report.quality_score > 95


@pytest.mark.asyncio
async def test_missing_and_invalid_counts_reduce_scores(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, missing_count=3, invalid_count=2,
    )

    assert report.completeness_pct == pytest.approx(70.0)
    assert report.validity_pct == pytest.approx(80.0)
    assert "3 record(s) with missing" in report.issues[0]
    assert "2 record(s) with invalid" in report.issues[1]


@pytest.mark.asyncio
async def test_duplicate_and_relationship_issues_reduce_consistency(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, relationship_issue_count=1, duplicate_count=2,
    )

    assert report.consistency_pct == pytest.approx(70.0)


@pytest.mark.asyncio
async def test_no_sync_history_gives_none_freshness_and_reliability(engine):
    report = await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=10)

    assert report.freshness_score is None
    assert report.reliability_score is None
    # quality_score still computed from whatever components ARE available (completeness/consistency)
    assert report.quality_score == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_stale_sync_reduces_freshness_score(engine, sync_run_repo):
    # ttl=1h, fully stale at ttl*5=5h — 3h old lands partway through the decay window.
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(hours=3), T0 - timedelta(hours=3)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, expected_update_frequency_seconds=3600,
    )

    assert 0 < report.freshness_score < 100


@pytest.mark.asyncio
async def test_very_stale_sync_gives_zero_freshness(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(days=30), T0 - timedelta(days=30)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, expected_update_frequency_seconds=3600,
    )

    assert report.freshness_score == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_reliability_reflects_mixed_recent_run_history(engine, sync_run_repo):
    for _ in range(3):
        await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(hours=1), T0 - timedelta(minutes=50)))
    await sync_run_repo.record(_run(SyncStatus.FAILED, T0 - timedelta(hours=2)))

    report = await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=10)

    assert report.reliability_score == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_reliability_window_excludes_old_runs(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))
    await sync_run_repo.record(_run(SyncStatus.FAILED, T0 - timedelta(days=30)))

    report = await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=10, reliability_window_days=7)

    assert report.reliability_score == pytest.approx(100.0)  # the failed run is outside the 7-day window


@pytest.mark.asyncio
async def test_coverage_pct_uses_total_expected(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=8, total_expected_records=10,
    )

    assert report.coverage_pct == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_coverage_pct_none_without_total_expected(engine, sync_run_repo):
    report = await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=8)

    assert report.coverage_pct is None


@pytest.mark.asyncio
async def test_provider_quality_score_delegates_to_port(engine, sync_run_repo, provider_reliability_port):
    provider_reliability_port.scores["api_football"] = 92.0
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))

    report = await engine.generate_report(
        "football", EntityKind.TEAM, T0, sample_size=10, provider_key="api_football",
    )

    assert report.provider_quality_score == pytest.approx(92.0)


@pytest.mark.asyncio
async def test_provider_quality_score_none_without_provider_key(engine, sync_run_repo):
    report = await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=10)

    assert report.provider_quality_score is None


@pytest.mark.asyncio
async def test_get_latest_and_list_history(engine, sync_run_repo):
    await sync_run_repo.record(_run(SyncStatus.SUCCEEDED, T0 - timedelta(minutes=5), T0 - timedelta(minutes=1)))
    await engine.generate_report("football", EntityKind.TEAM, T0, sample_size=10)
    await engine.generate_report("football", EntityKind.TEAM, T0 + timedelta(days=1), sample_size=12)

    latest = await engine.get_latest("football", EntityKind.TEAM)
    history = await engine.list_history("football", EntityKind.TEAM)

    assert latest.generated_at == T0 + timedelta(days=1)
    assert len(history) == 2
