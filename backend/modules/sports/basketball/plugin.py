"""Basketball sport plugin — implements modules.sports.ports.plugin_registry.SportPlugin."""

from __future__ import annotations

from dataclasses import dataclass

from modules.sports.domain.contracts.fixture import MatchEventTypeCatalog, MatchLifecycleRules
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema
from modules.sports.domain.value_objects import MatchPeriodKind, SportCode

MATCH_LIFECYCLE = MatchLifecycleRules(
    period_kind=MatchPeriodKind.QUARTER,
    regulation_periods=4,
    allows_overtime=True,
    allows_draw=False,
)

ROSTER_RULES = RosterRules(min_on_field=5, max_on_field=5, squad_size_max=15)

MATCH_EVENT_CATALOG = MatchEventTypeCatalog(
    event_types=frozenset(
        {
            "field_goal_made",
            "field_goal_missed",
            "three_point_made",
            "three_point_missed",
            "free_throw_made",
            "free_throw_missed",
            "rebound_offensive",
            "rebound_defensive",
            "assist",
            "steal",
            "block",
            "turnover",
            "foul",
            "timeout",
            "substitution",
        }
    )
)

TEAM_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("points", int),
        StatisticFieldSpec("field_goals_made", int),
        StatisticFieldSpec("field_goals_attempted", int),
        StatisticFieldSpec("rebounds", int),
        StatisticFieldSpec("turnovers", int),
    )
)

PLAYER_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("minutes_played", int),
        StatisticFieldSpec("points", int),
        StatisticFieldSpec("rebounds", int),
        StatisticFieldSpec("assists", int),
        StatisticFieldSpec("steals", int),
        StatisticFieldSpec("blocks", int),
    )
)

PLAYER_POSITIONS = frozenset(
    {"point_guard", "shooting_guard", "small_forward", "power_forward", "center"}
)


@dataclass(frozen=True)
class BasketballPlugin:
    code: SportCode = SportCode.BASKETBALL
    display_name: str = "Basketball"
    match_lifecycle: MatchLifecycleRules = MATCH_LIFECYCLE
    roster_rules: RosterRules = ROSTER_RULES
    match_event_catalog: MatchEventTypeCatalog = MATCH_EVENT_CATALOG
    team_statistic_schema: StatisticSchema = TEAM_STATISTIC_SCHEMA
    player_statistic_schema: StatisticSchema = PLAYER_STATISTIC_SCHEMA
    player_positions: frozenset[str] = PLAYER_POSITIONS


PLUGIN = BasketballPlugin()
