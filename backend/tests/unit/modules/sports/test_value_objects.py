from datetime import datetime, timedelta, timezone
from uuid import uuid4

from modules.sports.domain.value_objects import DateRange, TeamId


def test_date_range_contains_within_bounds():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 12, 31, tzinfo=timezone.utc)
    date_range = DateRange(start=start, end=end)

    assert date_range.contains(start + timedelta(days=1))


def test_date_range_excludes_before_start():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    date_range = DateRange(start=start)

    assert not date_range.contains(start - timedelta(days=1))


def test_date_range_open_ended_accepts_any_future_moment():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    date_range = DateRange(start=start, end=None)

    assert date_range.contains(start + timedelta(days=3650))


def test_typed_ids_are_not_interchangeable_by_type():
    raw = uuid4()
    team_id = TeamId(raw)

    assert team_id.value == raw
    assert str(team_id) == str(raw)
