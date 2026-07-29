from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.intelligence.domain.entities import IntelligenceSyncRun
from modules.intelligence.domain.value_objects import (
    IntelligenceChannelType,
    IntelligenceSyncRunId,
    SyncStatus,
    SyncTrigger,
    TrustLevel,
)

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _run(**overrides) -> IntelligenceSyncRun:
    defaults = dict(
        id=IntelligenceSyncRunId(uuid4()),
        channel_type=IntelligenceChannelType.NEWS,
        channel_key="source-1",
        trigger=SyncTrigger.SCHEDULED,
        status=SyncStatus.RUNNING,
        started_at=T0,
    )
    defaults.update(overrides)
    return IntelligenceSyncRun(**defaults)


def test_duration_seconds_is_none_while_running():
    run = _run()

    assert run.duration_seconds is None


def test_duration_seconds_computed_after_finish():
    run = _run()

    run.mark_succeeded(T0 + timedelta(seconds=30))

    assert run.duration_seconds == 30


def test_mark_succeeded_with_no_rejections_is_succeeded():
    run = _run(items_rejected=0)

    run.mark_succeeded(T0 + timedelta(seconds=5))

    assert run.status == SyncStatus.SUCCEEDED


def test_mark_succeeded_with_rejections_is_partial():
    run = _run(items_rejected=2)

    run.mark_succeeded(T0 + timedelta(seconds=5))

    assert run.status == SyncStatus.PARTIAL


def test_mark_failed_sets_error_message():
    run = _run()

    run.mark_failed(T0 + timedelta(seconds=5), "provider timeout")

    assert run.status == SyncStatus.FAILED
    assert run.error_message == "provider timeout"
    assert run.finished_at is not None


def test_trust_level_ordinal_ladder():
    assert TrustLevel.UNRELIABLE.level < TrustLevel.UNVERIFIED.level
    assert TrustLevel.UNVERIFIED.level < TrustLevel.VERIFIED.level
    assert TrustLevel.VERIFIED.level < TrustLevel.OFFICIAL.level
