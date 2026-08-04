import pytest

from modules.sports.domain.contracts.fixture import normalize_provider_fixture_status
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema
from modules.sports.domain.value_objects import FixtureStatus


def test_roster_rules_rejects_min_greater_than_max():
    with pytest.raises(ValueError):
        RosterRules(min_on_field=10, max_on_field=5)


def test_roster_rules_rejects_non_positive_counts():
    with pytest.raises(ValueError):
        RosterRules(min_on_field=0, max_on_field=5)


def test_statistic_schema_flags_missing_required_field():
    schema = StatisticSchema(fields=(StatisticFieldSpec("goals", int),))

    errors = schema.validate({})

    assert "missing required field 'goals'" in errors


def test_statistic_schema_flags_wrong_type():
    schema = StatisticSchema(fields=(StatisticFieldSpec("goals", int),))

    errors = schema.validate({"goals": "two"})

    assert any("expected int" in e for e in errors)


def test_statistic_schema_flags_unrecognized_field():
    schema = StatisticSchema(fields=(StatisticFieldSpec("goals", int),))

    errors = schema.validate({"goals": 2, "mystery_stat": 1})

    assert "unrecognized field 'mystery_stat'" in errors


def test_statistic_schema_allows_missing_optional_field():
    schema = StatisticSchema(fields=(StatisticFieldSpec("assists", int, required=False),))

    errors = schema.validate({})

    assert errors == []


def test_statistic_schema_valid_payload_has_no_errors():
    schema = StatisticSchema(
        fields=(StatisticFieldSpec("goals", int), StatisticFieldSpec("assists", int))
    )

    errors = schema.validate({"goals": 2, "assists": 1})

    assert errors == []


@pytest.mark.parametrize("raw", [None, ""])
def test_normalize_provider_fixture_status_defaults_to_scheduled_for_missing_status(raw):
    assert normalize_provider_fixture_status(raw) is FixtureStatus.SCHEDULED


@pytest.mark.parametrize("raw", ["NS", "TBD", "ns"])
def test_normalize_provider_fixture_status_recognizes_not_started_codes(raw):
    assert normalize_provider_fixture_status(raw) is FixtureStatus.SCHEDULED


@pytest.mark.parametrize("raw", ["FT", "AET", "PEN", "ft"])
def test_normalize_provider_fixture_status_recognizes_finished_codes(raw):
    assert normalize_provider_fixture_status(raw) is FixtureStatus.COMPLETED


@pytest.mark.parametrize("raw", ["PST", "SUSP", "INT"])
def test_normalize_provider_fixture_status_recognizes_postponed_codes(raw):
    assert normalize_provider_fixture_status(raw) is FixtureStatus.POSTPONED


@pytest.mark.parametrize("raw", ["CANC", "ABD"])
def test_normalize_provider_fixture_status_recognizes_cancelled_codes(raw):
    assert normalize_provider_fixture_status(raw) is FixtureStatus.CANCELLED


@pytest.mark.parametrize("raw", ["1H", "2H", "HT", "LIVE", "Q1", "IN5"])
def test_normalize_provider_fixture_status_falls_back_to_live_for_unrecognized_in_progress_codes(raw):
    # Unenumerated in-progress-shaped codes (basketball quarters, baseball innings, ...) must
    # still classify as LIVE rather than silently reverting to SCHEDULED.
    assert normalize_provider_fixture_status(raw) is FixtureStatus.LIVE
