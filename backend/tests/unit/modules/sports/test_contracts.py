import pytest

from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema


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
