"""Table tennis sport plugin — implements modules.sports.ports.plugin_registry.SportPlugin.

Note: no confirmed data provider yet for this sport (docs/titaniq.md §6, docs/roadmap.md
open items). This plugin exists so the domain/application layers can be built and tested now;
ingestion wiring is blocked on provider selection, not on this plugin.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.sports.domain.contracts.fixture import MatchEventTypeCatalog, MatchLifecycleRules
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticFieldSpec, StatisticSchema
from modules.sports.domain.value_objects import MatchPeriodKind, SportCode

MATCH_LIFECYCLE = MatchLifecycleRules(
    period_kind=MatchPeriodKind.SET,
    regulation_periods=5,  # best-of-5 default; best-of-7 competitions override at fixture level
    allows_overtime=False,
    allows_draw=False,
)

ROSTER_RULES = RosterRules(min_on_field=1, max_on_field=2, squad_size_max=None)

MATCH_EVENT_CATALOG = MatchEventTypeCatalog(
    event_types=frozenset(
        {
            "point_won",
            "service_fault",
            "let",
            "timeout_called",
            "game_point",
            "set_won",
        }
    )
)

TEAM_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("points_won", int),
        StatisticFieldSpec("sets_won", int),
        StatisticFieldSpec("unforced_errors", int),
    )
)

PLAYER_STATISTIC_SCHEMA = StatisticSchema(
    fields=(
        StatisticFieldSpec("points_won", int),
        StatisticFieldSpec("aces", int),
        StatisticFieldSpec("unforced_errors", int),
        StatisticFieldSpec("sets_won", int),
    )
)

PLAYER_POSITIONS = frozenset({"singles", "doubles"})


@dataclass(frozen=True)
class TableTennisPlugin:
    code: SportCode = SportCode.TABLE_TENNIS
    display_name: str = "Table Tennis"
    match_lifecycle: MatchLifecycleRules = MATCH_LIFECYCLE
    roster_rules: RosterRules = ROSTER_RULES
    match_event_catalog: MatchEventTypeCatalog = MATCH_EVENT_CATALOG
    team_statistic_schema: StatisticSchema = TEAM_STATISTIC_SCHEMA
    player_statistic_schema: StatisticSchema = PLAYER_STATISTIC_SCHEMA
    player_positions: frozenset[str] = PLAYER_POSITIONS


PLUGIN = TableTennisPlugin()
