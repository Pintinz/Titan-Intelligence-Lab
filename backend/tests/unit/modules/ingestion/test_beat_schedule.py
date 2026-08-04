import pytest

from modules.ingestion.infrastructure.celery.beat_schedule import BEAT_SCHEDULE, compute_adaptive_interval


def test_full_quota_uses_base_interval():
    assert compute_adaptive_interval(600, 100.0) == 600
    assert compute_adaptive_interval(600, 50.0) == 600


def test_moderate_quota_doubles_interval():
    assert compute_adaptive_interval(600, 49.9) == 1200
    assert compute_adaptive_interval(600, 20.0) == 1200


def test_low_quota_quadruples_interval():
    assert compute_adaptive_interval(600, 19.9) == 2400
    assert compute_adaptive_interval(600, 5.0) == 2400


def test_critical_quota_multiplies_by_eight():
    assert compute_adaptive_interval(600, 4.9) == 4800
    assert compute_adaptive_interval(600, 0.0) == 4800


def test_rejects_out_of_range_percentage():
    with pytest.raises(ValueError):
        compute_adaptive_interval(600, -1)
    with pytest.raises(ValueError):
        compute_adaptive_interval(600, 101)


def test_beat_schedule_entries_reference_registered_task_names():
    from modules.admin.infrastructure.celery import tasks as admin_tasks  # noqa: F401 — ensures admin.* tasks are registered
    from modules.ingestion.infrastructure.celery import tasks  # noqa: F401 — ensures ingestion.* tasks are registered
    from modules.ingestion.infrastructure.celery.celery_app import celery_app
    from modules.predictions.infrastructure.celery import tasks as predictions_tasks  # noqa: F401 — ensures predictions.* tasks are registered

    for entry in BEAT_SCHEDULE.values():
        assert entry["task"] in celery_app.tasks
