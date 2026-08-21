"""POST-M24 Phase 6 — deterministic tests for `market_line_resolution_service.py`.

Covers every resolver's normal/opposing/PUSH cases, the fixture-state gate (CANCELLED/POSTPONED/
not-yet-completed), and missing-line edge cases — no live provider data is exercised (none exists
yet, per the phase's verification report), only the pure resolution logic."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from modules.predictions.application.market_line_resolution_service import (
    resolve_market_line,
    resolve_moneyline,
    resolve_spread,
    resolve_total,
)
from modules.sports.domain.entities import MarketLine
from modules.sports.domain.value_objects import (
    FixtureId,
    FixtureStatus,
    LineSelection,
    MarketLineId,
    MarketLineOutcome,
    MarketLineType,
)

T0 = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _line(market_type: MarketLineType, selection: str, line: float | None, team_side: str | None = None) -> MarketLine:
    return MarketLine(
        id=MarketLineId(uuid4()), fixture_id=FixtureId(uuid4()), sport_code="basketball",
        provider="api_basketball", bookmaker="test_book", market_type=market_type, selection=selection,
        line=line, price=1.9, fetched_at=T0, team_side=team_side,
    )


# -- resolve_moneyline --------------------------------------------------------------------------


def test_moneyline_home_selection_wins_when_home_scores_more():
    assert resolve_moneyline(LineSelection.HOME, 101, 98) is MarketLineOutcome.WIN


def test_moneyline_home_selection_loses_when_away_scores_more():
    assert resolve_moneyline(LineSelection.HOME, 90, 95) is MarketLineOutcome.LOSS


def test_moneyline_away_selection_wins_when_away_scores_more():
    assert resolve_moneyline(LineSelection.AWAY, 90, 95) is MarketLineOutcome.WIN


def test_moneyline_unresolved_on_a_genuine_tie():
    """No stored line to push against — moneyline assumes a decisive winner, so a tie (an
    unmodeled scenario for a completed fixture) is UNKNOWN, never a guessed WIN/LOSS."""
    assert resolve_moneyline(LineSelection.HOME, 100, 100) is MarketLineOutcome.UNKNOWN


# -- resolve_spread ------------------------------------------------------------------------------


def test_spread_home_favorite_covers():
    # home -4.5, wins by 6 -> covers
    assert resolve_spread(LineSelection.HOME, -4.5, 101, 95) is MarketLineOutcome.WIN


def test_spread_home_favorite_fails_to_cover():
    # home -4.5, wins by only 3 -> doesn't cover
    assert resolve_spread(LineSelection.HOME, -4.5, 101, 98) is MarketLineOutcome.LOSS


def test_spread_away_underdog_covers_on_a_narrow_loss():
    # away +4.5, loses by 3 -> covers
    assert resolve_spread(LineSelection.AWAY, 4.5, 101, 98) is MarketLineOutcome.WIN


def test_spread_exact_whole_number_line_pushes():
    # home -4.0, wins by exactly 4 -> PUSH
    assert resolve_spread(LineSelection.HOME, -4.0, 100, 96) is MarketLineOutcome.PUSH


# -- resolve_total ---------------------------------------------------------------------------


def test_total_over_wins_when_total_exceeds_line():
    assert resolve_total(LineSelection.OVER, 220.5, 231) is MarketLineOutcome.WIN


def test_total_under_wins_when_total_is_below_line():
    assert resolve_total(LineSelection.UNDER, 220.5, 199) is MarketLineOutcome.WIN


def test_total_over_loses_when_total_is_below_line():
    assert resolve_total(LineSelection.OVER, 220.5, 199) is MarketLineOutcome.LOSS


def test_total_exact_whole_number_line_pushes():
    assert resolve_total(LineSelection.OVER, 199, 199) is MarketLineOutcome.PUSH
    assert resolve_total(LineSelection.UNDER, 199, 199) is MarketLineOutcome.PUSH


# -- resolve_market_line: dispatch + fixture-state gate -------------------------------------------


def test_resolve_market_line_dispatches_moneyline():
    line = _line(MarketLineType.MONEYLINE, "HOME", None)
    assert resolve_market_line(line, 101, 98, FixtureStatus.COMPLETED) is MarketLineOutcome.WIN


def test_resolve_market_line_dispatches_spread():
    line = _line(MarketLineType.SPREAD, "HOME", -4.5)
    assert resolve_market_line(line, 101, 95, FixtureStatus.COMPLETED) is MarketLineOutcome.WIN


def test_resolve_market_line_dispatches_total():
    line = _line(MarketLineType.TOTAL, "OVER", 220.5)
    assert resolve_market_line(line, 120, 111, FixtureStatus.COMPLETED) is MarketLineOutcome.WIN


def test_resolve_market_line_dispatches_team_total_home_side():
    line = _line(MarketLineType.TEAM_TOTAL, "OVER", 110.5, team_side="HOME")
    assert resolve_market_line(line, 115, 90, FixtureStatus.COMPLETED) is MarketLineOutcome.WIN


def test_resolve_market_line_dispatches_team_total_away_side():
    line = _line(MarketLineType.TEAM_TOTAL, "UNDER", 100.5, team_side="AWAY")
    assert resolve_market_line(line, 115, 90, FixtureStatus.COMPLETED) is MarketLineOutcome.WIN


def test_resolve_market_line_team_total_unknown_without_a_side():
    """A TEAM_TOTAL line with no `team_side` cannot be resolved — never guessed which team it
    was quoted for."""
    line = _line(MarketLineType.TEAM_TOTAL, "OVER", 110.5, team_side=None)
    assert resolve_market_line(line, 115, 90, FixtureStatus.COMPLETED) is MarketLineOutcome.UNKNOWN


def test_resolve_market_line_cancelled_fixture_voids_the_line():
    line = _line(MarketLineType.MONEYLINE, "HOME", None)
    assert resolve_market_line(line, None, None, FixtureStatus.CANCELLED) is MarketLineOutcome.CANCELLED


def test_resolve_market_line_postponed_fixture_is_void():
    line = _line(MarketLineType.SPREAD, "HOME", -4.5)
    assert resolve_market_line(line, None, None, FixtureStatus.POSTPONED) is MarketLineOutcome.VOID


def test_resolve_market_line_unresolved_before_the_fixture_completes():
    line = _line(MarketLineType.TOTAL, "OVER", 220.5)
    assert resolve_market_line(line, None, None, FixtureStatus.LIVE) is MarketLineOutcome.UNKNOWN
    assert resolve_market_line(line, None, None, FixtureStatus.SCHEDULED) is MarketLineOutcome.UNKNOWN


def test_resolve_market_line_unresolved_when_line_value_is_missing():
    """A SPREAD/TOTAL entity with `line=None` is a malformed/incomplete quote — never resolved
    as if a real line existed."""
    line = _line(MarketLineType.SPREAD, "HOME", None)
    assert resolve_market_line(line, 101, 95, FixtureStatus.COMPLETED) is MarketLineOutcome.UNKNOWN
