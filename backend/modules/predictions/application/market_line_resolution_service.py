"""POST-M24 Phase 6 — resolves a real, persisted `MarketLine` against a fixture's actual result.

Deliberately separate from `outcome_resolution_service.py`: every existing resolver there
assumes a binary WIN/LOSS (or a fixed three-way HOME_WIN/DRAW/AWAY_WIN) because none of them
depend on a variable, provider-supplied number. A market line genuinely can PUSH (exact equality
against an integer line) or go VOID/CANCELLED (the fixture never reached a resolvable state) —
states a market with no stored line structurally cannot produce. Collapsing PUSH into WIN or LOSS
here would silently misrepresent a real, common sportsbook outcome, so it never happens.

Pure functions only — no I/O, no persistence. Real market-line data does not yet exist anywhere
in TitanIQ's database (Phase 6 audit: the provider endpoint is reachable but returns nothing for
any fixture currently ingested), so this module is exercised by direct unit tests today, not by
any production caller — building it now, correctly, means the day real lines are ingested, the
resolution logic does not need to be invented under time pressure with unverified data.
"""

from __future__ import annotations

from modules.sports.domain.entities import MarketLine
from modules.sports.domain.value_objects import FixtureStatus, LineSelection, MarketLineOutcome, MarketLineType


def resolve_moneyline(selection: LineSelection, home_score: int, away_score: int) -> MarketLineOutcome:
    """No stored line — price only. A moneyline market assumes a decisive winner; an actual tie
    (a genuinely unmodeled scenario for a completed basketball/baseball fixture) resolves to
    UNKNOWN, never guessed as a WIN or LOSS."""
    if home_score == away_score:
        return MarketLineOutcome.UNKNOWN
    home_won = home_score > away_score
    won = (selection is LineSelection.HOME and home_won) or (selection is LineSelection.AWAY and not home_won)
    return MarketLineOutcome.WIN if won else MarketLineOutcome.LOSS


def resolve_spread(selection: LineSelection, line: float, home_score: int, away_score: int) -> MarketLineOutcome:
    """Standard point-spread convention: the selected side's own margin plus its own line value.
    Exact zero is a real PUSH (only reachable when `line` is a whole number, e.g. -4.0 against an
    actual 4-point margin) — never rounded away."""
    margin = home_score - away_score
    adjusted = (margin + line) if selection is LineSelection.HOME else (-margin + line)
    if adjusted > 0:
        return MarketLineOutcome.WIN
    if adjusted == 0:
        return MarketLineOutcome.PUSH
    return MarketLineOutcome.LOSS


def resolve_total(selection: LineSelection, line: float, total: int) -> MarketLineOutcome:
    """Game or team total over/under. Exact equality against an integer `total` and a whole-number
    `line` is a real PUSH, not a rounding artifact to collapse into a side."""
    if total == line:
        return MarketLineOutcome.PUSH
    over = total > line
    won = (selection is LineSelection.OVER and over) or (selection is LineSelection.UNDER and not over)
    return MarketLineOutcome.WIN if won else MarketLineOutcome.LOSS


def resolve_market_line(
    market_line: MarketLine, home_score: int | None, away_score: int | None, fixture_status: FixtureStatus,
) -> MarketLineOutcome:
    """The single entry point a future orchestrator calls — dispatches by `market_line.market_type`
    to the pure functions above, and applies the fixture-state gate every real sportsbook applies
    before ever asking "who won": a cancelled fixture voids every line on it outright; a fixture
    that hasn't reached a final score yet is not resolvable at all (returns UNKNOWN, never guessed
    from a partial score)."""
    if fixture_status in (FixtureStatus.CANCELLED,):
        return MarketLineOutcome.CANCELLED
    if fixture_status is FixtureStatus.POSTPONED:
        return MarketLineOutcome.VOID
    if fixture_status is not FixtureStatus.COMPLETED or home_score is None or away_score is None:
        return MarketLineOutcome.UNKNOWN

    selection = LineSelection(market_line.selection)

    if market_line.market_type is MarketLineType.MONEYLINE:
        return resolve_moneyline(selection, home_score, away_score)

    if market_line.market_type is MarketLineType.SPREAD:
        if market_line.line is None:
            return MarketLineOutcome.UNKNOWN
        return resolve_spread(selection, market_line.line, home_score, away_score)

    if market_line.market_type is MarketLineType.TOTAL:
        if market_line.line is None:
            return MarketLineOutcome.UNKNOWN
        return resolve_total(selection, market_line.line, home_score + away_score)

    if market_line.market_type is MarketLineType.TEAM_TOTAL:
        if market_line.line is None or market_line.team_side is None:
            return MarketLineOutcome.UNKNOWN
        team_score = home_score if market_line.team_side == "HOME" else away_score
        return resolve_total(selection, market_line.line, team_score)

    return MarketLineOutcome.UNKNOWN
