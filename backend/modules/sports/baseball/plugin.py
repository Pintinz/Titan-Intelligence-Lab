"""Baseball sport plugin — implements modules.sports.ports.plugin_registry.SportPlugin."""

from __future__ import annotations

from dataclasses import dataclass

from modules.sports.domain.contracts.fixture import MatchEventTypeCatalog, MatchLifecycleRules
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema
from modules.sports.domain.value_objects import MatchPeriodKind, SportCode

MATCH_LIFECYCLE = MatchLifecycleRules(
    period_kind=MatchPeriodKind.INNING,
    regulation_periods=9,
    allows_overtime=True,  # extra innings
    allows_draw=False,
)

ROSTER_RULES = RosterRules(min_on_field=9, max_on_field=9, squad_size_max=26)

MATCH_EVENT_CATALOG = MatchEventTypeCatalog(
    event_types=frozenset(
        {
            "single",
            "double",
            "triple",
            "home_run",
            "walk",
            "strikeout",
            "stolen_base",
            "error",
            "sacrifice_fly",
            "hit_by_pitch",
            "pitching_change",
        }
    )
)

TEAM_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("runs", int),
        StatisticFieldSpec("hits", int),
        StatisticFieldSpec("errors", int),
        StatisticFieldSpec("left_on_base", int),
    )
)

PLAYER_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("at_bats", int),
        StatisticFieldSpec("hits", int),
        StatisticFieldSpec("runs", int),
        StatisticFieldSpec("rbi", int),
        StatisticFieldSpec("strikeouts", int),
        StatisticFieldSpec("innings_pitched", float, required=False),
    )
)

PLAYER_POSITIONS = frozenset(
    {
        "pitcher",
        "catcher",
        "first_base",
        "second_base",
        "third_base",
        "shortstop",
        "left_field",
        "center_field",
        "right_field",
        "designated_hitter",
    }
)


@dataclass(frozen=True)
class BaseballPlugin:
    code: SportCode = SportCode.BASEBALL
    display_name: str = "Baseball"
    match_lifecycle: MatchLifecycleRules = MATCH_LIFECYCLE
    roster_rules: RosterRules = ROSTER_RULES
    match_event_catalog: MatchEventTypeCatalog = MATCH_EVENT_CATALOG
    team_statistic_schema: StatisticSchema = TEAM_STATISTIC_SCHEMA
    player_statistic_schema: StatisticSchema = PLAYER_STATISTIC_SCHEMA
    player_positions: frozenset[str] = PLAYER_POSITIONS


PLUGIN = BaseballPlugin()
