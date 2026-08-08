"""Market Outcome Registry (Milestone 9.2 — Market Registry & Prediction Domain Normalization,
Phase 1: foundation only).

This module is the explicit answer to the audit's central finding: `Prediction.value` currently
stores the generic predictor strategy's bare output (``"positive"``/``"negative"``/a raw number
string) with no market-specific real-world meaning anywhere in the codebase. `MARKET_OUTCOME_CATALOG`
below is that missing specification — for every market this platform's brief names, across all
four sports, it states explicitly what the market's real answer looks like (`OutcomeType`) and
the exact set of values a resolved prediction for that market may take (`allowed_values`).

Phase 1 scope, deliberately: this is a *catalog* — a comprehensive, explicit specification of the
target outcome-label contract per market. It does **not** change what any predictor emits, does
not touch `PredictionEngine.generate()`, does not modify `OutcomeResolutionService`, evaluation,
calibration, retraining, or the Gemini explanation pipeline, and does not migrate the 28 existing
``"positive"``/``"negative"`` draft predictions already in the database. Wiring predictors and the
evaluation pipeline to actually produce/consume these labels is later-phase work, intentionally
excluded here. Six entries below (`resolver_key` set) already have a real, tested resolver wired
in `modules.predictions.application.outcome_resolution_service.MARKET_OUTCOME_RESOLVERS` — for
those, `resolver_key` names the exact key in that dict. Every other entry's `resolver_key` is
``None``: a real resolver for it doesn't exist yet, and this catalog does not claim otherwise.

Milestone 9.2 Phase 3 added a seventh resolver, of a genuinely different shape: `football.match_winner`'s
`resolver_key` points into `outcome_resolution_service.THREE_WAY_MARKET_RESOLVERS` (direct label
equality — HOME_WIN/DRAW/AWAY_WIN has no affirmative/negative side to check polarity against), not
`MARKET_OUTCOME_RESOLVERS` like the other six.

**Football market catalog expansion (2026-08-02)** added nine more real resolvers, all computable
from a fixture's full-time score alone (four more total-goals lines, away team goals, home/away
clean sheet, home/away win-to-nil) — sixteen resolver_key entries total now. Also added, correctly
left unresolved: first-half goals, first-half BTTS, and second-half winner all need sub-match
score data this platform doesn't ingest yet (the same honest gap `football.first_half_winner`
already had); Double Chance and Goal Range are deliberately NOT seeded as live markets at all —
Double Chance is mathematically derived from `football.match_winner`'s own HOME_DRAW_AWAY
distribution (P(1X) = P(H)+P(D), etc.), not an independently-trained model, and building that
derivation is separate Derived-Intelligence work; Goal Range (4-way score-bucket classification)
doesn't fit any existing `MarketKind` predictor strategy without inventing one. Both stay as
specification-only catalog entries (no seeded `MarketDefinition`, no resolver) — flagged, not
fabricated.

Not every market in this catalog has a corresponding registered `MarketDefinition` row today —
this module is the specification live registrations are built from, so the label contract is
decided once, explicitly, rather than invented ad hoc per market as it's built.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.predictions.domain.value_objects import OutcomeType


@dataclass(frozen=True)
class MarketOutcomeSpec:
    market_key: str
    sport_code: str
    name: str
    outcome_type: OutcomeType
    allowed_values: tuple[str, ...]
    # Key into `outcome_resolution_service.MARKET_OUTCOME_RESOLVERS` when a real resolver exists
    # for this market today; None means the resolver is specified here but not yet implemented.
    resolver_key: str | None = None


def _correct_score_grid(max_goals: int = 5) -> tuple[str, ...]:
    """A finite scoreline grid (0-0 through `max_goals`-`max_goals`) plus an "OTHER" catch-all for
    any score outside it — the same finite-grid-plus-catch-all shape real sportsbooks use for
    correct-score markets, rather than an unbounded (and therefore useless as a classification
    target) set of every mathematically possible score."""
    grid = tuple(f"{home}-{away}" for home in range(max_goals + 1) for away in range(max_goals + 1))
    return grid + ("OTHER",)


_OU = OutcomeType.OVER_UNDER
_OVER_UNDER_VALUES = ("OVER", "UNDER")

MARKET_OUTCOME_CATALOG: dict[str, MarketOutcomeSpec] = {
    # -- Football -------------------------------------------------------------------------------
    "football.match_winner": MarketOutcomeSpec(
        "football.match_winner", "football", "Match Winner",
        OutcomeType.HOME_DRAW_AWAY, ("HOME_WIN", "DRAW", "AWAY_WIN"),
        resolver_key="football.match_winner",
    ),
    # The ad-hoc market real dev.db predictions were generated against (see this module's
    # docstring) — same 3-way shape as football.match_winner, kept as its own catalog entry since
    # it's a distinct, already-seeded `market_key`, not an alias.
    "football.match_result": MarketOutcomeSpec(
        "football.match_result", "football", "Match Result",
        OutcomeType.HOME_DRAW_AWAY, ("HOME_WIN", "DRAW", "AWAY_WIN"),
    ),
    "football.double_chance": MarketOutcomeSpec(
        "football.double_chance", "football", "Double Chance",
        OutcomeType.DOUBLE_CHANCE, ("HOME_OR_DRAW", "HOME_OR_AWAY", "DRAW_OR_AWAY"),
    ),
    "football.both_teams_to_score": MarketOutcomeSpec(
        "football.both_teams_to_score", "football", "Both Teams To Score",
        OutcomeType.BINARY_YES_NO, ("YES", "NO"), resolver_key="football.both_teams_to_score",
    ),
    "football.total_goals_over_under_0_5": MarketOutcomeSpec(
        "football.total_goals_over_under_0_5", "football", "Total Goals Over/Under 0.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.total_goals_over_under_0_5",
    ),
    "football.total_goals_over_under_1_5": MarketOutcomeSpec(
        "football.total_goals_over_under_1_5", "football", "Total Goals Over/Under 1.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.total_goals_over_under_1_5",
    ),
    "football.total_goals_over_under_2_5": MarketOutcomeSpec(
        "football.total_goals_over_under_2_5", "football", "Total Goals Over/Under 2.5", _OU, _OVER_UNDER_VALUES,
    ),
    "football.total_goals_over_under_3_5": MarketOutcomeSpec(
        "football.total_goals_over_under_3_5", "football", "Total Goals Over/Under 3.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.total_goals_over_under_3_5",
    ),
    "football.total_goals_over_under_4_5": MarketOutcomeSpec(
        "football.total_goals_over_under_4_5", "football", "Total Goals Over/Under 4.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.total_goals_over_under_4_5",
    ),
    # Already-seeded market_key (market_seeding.py) — same OVER_UNDER shape as the *_2_5 entry
    # above, kept distinct since it's the real, currently-production market_key, not a duplicate.
    "football.total_goals_over_under": MarketOutcomeSpec(
        "football.total_goals_over_under", "football", "Total Goals Over/Under 2.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.total_goals_over_under",
    ),
    "football.home_team_total_0_5": MarketOutcomeSpec(
        "football.home_team_total_0_5", "football", "Home Team Total Goals Over/Under 0.5", _OU, _OVER_UNDER_VALUES,
    ),
    "football.home_team_total_1_5": MarketOutcomeSpec(
        "football.home_team_total_1_5", "football", "Home Team Total Goals Over/Under 1.5", _OU, _OVER_UNDER_VALUES,
    ),
    "football.home_team_total_goals": MarketOutcomeSpec(
        "football.home_team_total_goals", "football", "Home Team Total Goals Over/Under 1.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.home_team_total_goals",
    ),
    "football.away_team_total_0_5": MarketOutcomeSpec(
        "football.away_team_total_0_5", "football", "Away Team Total Goals Over/Under 0.5", _OU, _OVER_UNDER_VALUES,
    ),
    "football.away_team_total_1_5": MarketOutcomeSpec(
        "football.away_team_total_1_5", "football", "Away Team Total Goals Over/Under 1.5", _OU, _OVER_UNDER_VALUES,
    ),
    # Real, seeded market_key — mirrors football.home_team_total_goals's own naming/line (1.5).
    "football.away_team_total_goals": MarketOutcomeSpec(
        "football.away_team_total_goals", "football", "Away Team Total Goals Over/Under 1.5", _OU, _OVER_UNDER_VALUES,
        resolver_key="football.away_team_total_goals",
    ),
    "football.correct_score": MarketOutcomeSpec(
        "football.correct_score", "football", "Correct Score", OutcomeType.CORRECT_SCORE, _correct_score_grid(),
        # Audit fix (2026-08-06): this market never had a resolver_key, unlike every other member
        # of NOT_YET_TRAINED_MARKET_KEYS — the reason its outcomes never accumulated even before
        # the Poisson-predictor removal. See outcome_resolution_service.py's GRID_MARKET_RESOLVERS.
        resolver_key="football.correct_score",
    ),
    "football.home_clean_sheet": MarketOutcomeSpec(
        "football.home_clean_sheet", "football", "Home Clean Sheet", OutcomeType.BINARY_YES_NO, ("YES", "NO"),
        resolver_key="football.home_clean_sheet",
    ),
    "football.away_clean_sheet": MarketOutcomeSpec(
        "football.away_clean_sheet", "football", "Away Clean Sheet", OutcomeType.BINARY_YES_NO, ("YES", "NO"),
        resolver_key="football.away_clean_sheet",
    ),
    "football.home_win_to_nil": MarketOutcomeSpec(
        "football.home_win_to_nil", "football", "Home Win To Nil", OutcomeType.BINARY_YES_NO, ("YES", "NO"),
        resolver_key="football.home_win_to_nil",
    ),
    "football.away_win_to_nil": MarketOutcomeSpec(
        "football.away_win_to_nil", "football", "Away Win To Nil", OutcomeType.BINARY_YES_NO, ("YES", "NO"),
        resolver_key="football.away_win_to_nil",
    ),
    # No resolver: needs first/second-half sub-match score data this platform doesn't ingest yet
    # (same documented gap as football.first_half_winner, seeded but unresolved for the same reason).
    "football.first_half_winner": MarketOutcomeSpec(
        "football.first_half_winner", "football", "First Half Winner", OutcomeType.HOME_DRAW_AWAY,
        ("HOME_WIN", "DRAW", "AWAY_WIN"),
    ),
    "football.second_half_winner": MarketOutcomeSpec(
        "football.second_half_winner", "football", "Second Half Winner", OutcomeType.HOME_DRAW_AWAY,
        ("HOME_WIN", "DRAW", "AWAY_WIN"),
    ),
    "football.first_half_goals": MarketOutcomeSpec(
        "football.first_half_goals", "football", "First Half Goals Over/Under 0.5", _OU, _OVER_UNDER_VALUES,
    ),
    "football.first_half_both_teams_to_score": MarketOutcomeSpec(
        "football.first_half_both_teams_to_score", "football", "First Half Both Teams To Score",
        OutcomeType.BINARY_YES_NO, ("YES", "NO"),
    ),
    # Specification-only, deliberately not seeded as a live market (see module docstring): a
    # 4-way score-bucket classification with no existing MarketKind predictor strategy to serve it.
    "football.goal_range": MarketOutcomeSpec(
        "football.goal_range", "football", "Goal Range", OutcomeType.GOAL_RANGE,
        ("0-1", "2-3", "4-5", "6+"),
    ),

    # -- Basketball -------------------------------------------------------------------------------
    "basketball.winner": MarketOutcomeSpec(
        "basketball.winner", "basketball", "Winner", OutcomeType.HOME_AWAY, ("HOME_WIN", "AWAY_WIN"),
    ),
    "basketball.moneyline": MarketOutcomeSpec(
        "basketball.moneyline", "basketball", "Moneyline", OutcomeType.HOME_AWAY, ("HOME", "AWAY"),
        resolver_key="basketball.moneyline",
    ),
    "basketball.spread": MarketOutcomeSpec(
        "basketball.spread", "basketball", "Spread",
        OutcomeType.HOME_COVER_AWAY_COVER, ("HOME_COVER", "AWAY_COVER"),
    ),
    "basketball.totals": MarketOutcomeSpec(
        "basketball.totals", "basketball", "Totals", _OU, _OVER_UNDER_VALUES,
    ),
    "basketball.quarter_winner": MarketOutcomeSpec(
        "basketball.quarter_winner", "basketball", "Quarter Winner", OutcomeType.HOME_AWAY, ("HOME", "AWAY"),
    ),
    "basketball.half_winner": MarketOutcomeSpec(
        "basketball.half_winner", "basketball", "Half Winner", OutcomeType.HOME_AWAY, ("HOME", "AWAY"),
    ),

    # -- Baseball ---------------------------------------------------------------------------------
    "baseball.winner": MarketOutcomeSpec(
        "baseball.winner", "baseball", "Winner", OutcomeType.HOME_AWAY, ("HOME_WIN", "AWAY_WIN"),
        resolver_key="baseball.moneyline",
    ),
    # The actually-seeded market_key (baseball/market_seeding.py) behind the resolver above —
    # same shape as "baseball.winner", kept as its own entry since it's the real, currently-
    # production `market_key`, not an alias (mirrors football.total_goals_over_under's pattern).
    "baseball.moneyline": MarketOutcomeSpec(
        "baseball.moneyline", "baseball", "Moneyline", OutcomeType.HOME_AWAY, ("HOME_WIN", "AWAY_WIN"),
        resolver_key="baseball.moneyline",
    ),
    "baseball.run_line": MarketOutcomeSpec(
        "baseball.run_line", "baseball", "Run Line",
        OutcomeType.HOME_COVER_AWAY_COVER, ("HOME_COVER", "AWAY_COVER"),
    ),
    "baseball.totals": MarketOutcomeSpec(
        "baseball.totals", "baseball", "Totals", _OU, _OVER_UNDER_VALUES,
    ),

    # -- Table Tennis -----------------------------------------------------------------------------
    "table_tennis.winner": MarketOutcomeSpec(
        "table_tennis.winner", "table_tennis", "Winner", OutcomeType.HOME_AWAY, ("HOME_WIN", "AWAY_WIN"),
        resolver_key="table_tennis.match_winner",
    ),
    # The actually-seeded market_key (table_tennis/market_seeding.py) — same shape as
    # "table_tennis.winner" above, kept as its own entry for the same reason baseball.moneyline is.
    "table_tennis.match_winner": MarketOutcomeSpec(
        "table_tennis.match_winner", "table_tennis", "Match Winner", OutcomeType.HOME_AWAY, ("HOME_WIN", "AWAY_WIN"),
        resolver_key="table_tennis.match_winner",
    ),
    "table_tennis.correct_sets": MarketOutcomeSpec(
        "table_tennis.correct_sets", "table_tennis", "Correct Sets",
        OutcomeType.CORRECT_SET_SCORE, ("3-0", "3-1", "3-2", "0-3", "1-3", "2-3"),
    ),
}


def get_outcome_spec(market_key: str) -> MarketOutcomeSpec | None:
    return MARKET_OUTCOME_CATALOG.get(market_key)
