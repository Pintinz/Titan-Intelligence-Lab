"""POST-M24 Phase 5A — pure-function tests for `_extract_half_time_scores` (extended to handle
basketball's `kind="quarter"`) and `_extract_first_five_innings_scores` (new, baseball
`kind="inning"`). Both read `Fixture.period_scores` only — never derived from the final score.

Phase 5B adds `_extract_quarter_scores` (basketball's individual per-quarter breakdown, backing
the Q1-Q4 winner markets)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.ingestion.application.entity_reconciliation_service import (
    _extract_first_five_innings_scores,
    _extract_half_time_scores,
    _extract_quarter_scores,
)
from modules.sports.domain.entities import Fixture
from modules.sports.domain.value_objects import FixtureId, FixtureStatus, SeasonId, TeamId

T0 = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _fixture(period_scores: dict | None) -> Fixture:
    return Fixture(
        id=FixtureId(uuid4()), season_id=SeasonId(uuid4()), home_team_id=TeamId(uuid4()), away_team_id=TeamId(uuid4()),
        venue_id=None, scheduled_at=T0, status=FixtureStatus.COMPLETED, version=1,
        home_score=100, away_score=90, period_scores=period_scores,
    )


# -- _extract_half_time_scores: football (kind="half") — unchanged behavior -----------------------


def test_football_half_kind_returns_first_element():
    fixture = _fixture({"kind": "half", "home": [1, 1], "away": [0, 2]})
    assert _extract_half_time_scores(fixture) == (1, 0)


def test_no_period_scores_returns_none_none():
    fixture = _fixture(None)
    assert _extract_half_time_scores(fixture) == (None, None)


# -- _extract_half_time_scores: basketball (kind="quarter") — new this phase -----------------------


def test_basketball_quarter_kind_sums_first_two_quarters():
    fixture = _fixture({"kind": "quarter", "home": [30, 24, 21, 26], "away": [28, 22, 25, 23]})
    assert _extract_half_time_scores(fixture) == (54, 50)


def test_basketball_quarter_kind_unresolved_before_second_quarter_recorded():
    fixture = _fixture({"kind": "quarter", "home": [30], "away": [28]})
    assert _extract_half_time_scores(fixture) == (None, None)


def test_basketball_quarter_kind_unresolved_on_null_quarter():
    fixture = _fixture({"kind": "quarter", "home": [30, None, 21, 26], "away": [28, 22, 25, 23]})
    assert _extract_half_time_scores(fixture) == (None, None)


def test_unknown_kind_returns_none_none():
    fixture = _fixture({"kind": "set", "home": [11, 11], "away": [9, 7]})
    assert _extract_half_time_scores(fixture) == (None, None)


# -- _extract_first_five_innings_scores: baseball (kind="inning") — new this phase -----------------


def test_baseball_inning_kind_sums_first_five_innings():
    fixture = _fixture({"kind": "inning", "home": [2, 0, 0, 2, 1, 0, 0, 0, 1], "away": [0, 3, 0, 0, 0, 0, 1, 1, 0]})
    assert _extract_first_five_innings_scores(fixture) == (5, 3)


def test_baseball_inning_kind_unresolved_when_fewer_than_five_innings_recorded():
    fixture = _fixture({"kind": "inning", "home": [1, 0, 0], "away": [0, 1, 0]})
    assert _extract_first_five_innings_scores(fixture) == (None, None)


def test_baseball_inning_kind_unresolved_on_null_within_first_five():
    """A walk-off win before the away team completed its half of an early inning — never
    fabricated as zero."""
    fixture = _fixture({"kind": "inning", "home": [1, 0, 0, 0, None, None, None, None, None], "away": [0, 0, 0, 0, None, None, None, None, None]})
    assert _extract_first_five_innings_scores(fixture) == (None, None)


def test_baseball_inning_kind_not_confused_with_basketball_quarter_kind():
    fixture = _fixture({"kind": "quarter", "home": [30, 24, 21, 26], "away": [28, 22, 25, 23]})
    assert _extract_first_five_innings_scores(fixture) == (None, None)


# -- _extract_quarter_scores: basketball (kind="quarter") — new Phase 5B ---------------------------


def test_extract_quarter_scores_returns_the_full_tuple():
    fixture = _fixture({"kind": "quarter", "home": [30, 24, 21, 26], "away": [28, 22, 25, 23]})
    assert _extract_quarter_scores(fixture) == ((30, 24, 21, 26), (28, 22, 25, 23))


def test_extract_quarter_scores_no_period_scores_returns_none_none():
    fixture = _fixture(None)
    assert _extract_quarter_scores(fixture) == (None, None)


def test_extract_quarter_scores_wrong_kind_returns_none_none():
    fixture = _fixture({"kind": "inning", "home": [1, 0, 0, 2, 1, 0, 0, 0, 1], "away": [0, 3, 0, 0, 0, 0, 1, 1, 0]})
    assert _extract_quarter_scores(fixture) == (None, None)


def test_extract_quarter_scores_preserves_a_partial_tuple_for_downstream_resolvers_to_reject():
    """A game abandoned mid-Q3 legitimately has only 2 recorded quarters — this function itself
    doesn't decide resolvability, the quarter-winner resolvers do (their own `quarter_index >=
    len(...)` guard), so it returns the real partial tuple, never pads it."""
    fixture = _fixture({"kind": "quarter", "home": [30, 24], "away": [28, 22]})
    assert _extract_quarter_scores(fixture) == ((30, 24), (28, 22))
