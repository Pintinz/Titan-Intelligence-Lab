"""Football sport plugin — implements modules.sports.ports.plugin_registry.SportPlugin.

No provider wiring here (that starts in Milestone 3) — this is the sport's structural
declaration only: match shape, roster bounds, recognized events, and statistic schemas.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.sports.domain.contracts.fixture import MatchEventTypeCatalog, MatchLifecycleRules
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema
from modules.sports.domain.value_objects import MatchPeriodKind, SportCode

MATCH_LIFECYCLE = MatchLifecycleRules(
    period_kind=MatchPeriodKind.HALF,
    regulation_periods=2,
    allows_overtime=True,
    allows_draw=True,
)

ROSTER_RULES = RosterRules(min_on_field=11, max_on_field=11, squad_size_max=25)

MATCH_EVENT_CATALOG = MatchEventTypeCatalog(
    event_types=frozenset(
        {
            "goal",
            "own_goal",
            "penalty_scored",
            "penalty_missed",
            "yellow_card",
            "red_card",
            "substitution",
            "corner",
            "offside",
            "foul",
            "var_review",
        }
    )
)

TEAM_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("possession_pct", float),
        StatisticFieldSpec("shots_total", int),
        StatisticFieldSpec("shots_on_target", int),
        StatisticFieldSpec("corners", int),
        StatisticFieldSpec("fouls", int),
    )
)

PLAYER_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("minutes_played", int),
        StatisticFieldSpec("goals", int),
        StatisticFieldSpec("assists", int),
        StatisticFieldSpec("shots", int),
        StatisticFieldSpec("passes_completed", int),
    )
)

PLAYER_POSITIONS = frozenset({"goalkeeper", "defender", "midfielder", "forward"})


@dataclass(frozen=True)
class FootballPlugin:
    code: SportCode = SportCode.FOOTBALL
    display_name: str = "Football"
    match_lifecycle: MatchLifecycleRules = MATCH_LIFECYCLE
    roster_rules: RosterRules = ROSTER_RULES
    match_event_catalog: MatchEventTypeCatalog = MATCH_EVENT_CATALOG
    team_statistic_schema: StatisticSchema = TEAM_STATISTIC_SCHEMA
    player_statistic_schema: StatisticSchema = PLAYER_STATISTIC_SCHEMA
    player_positions: frozenset[str] = PLAYER_POSITIONS


PLUGIN = FootballPlugin()
