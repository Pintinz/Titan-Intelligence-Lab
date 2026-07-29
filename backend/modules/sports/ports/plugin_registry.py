"""Sport plugin port — the contract every per-sport package (football/, basketball/,
baseball/, table_tennis/) implements, and the registry application code resolves plugins
through. New sports register here without any other module changing (docs/architecture.md §4).
"""

from __future__ import annotations

from typing import Protocol

from modules.sports.domain.contracts.fixture import MatchEventTypeCatalog, MatchLifecycleRules
from modules.sports.domain.contracts.participant import RosterRules
from modules.sports.domain.contracts.statistics import StatisticSchema
from modules.sports.domain.value_objects import SportCode


class SportPlugin(Protocol):
    """Everything generic code needs to know about a sport, without naming it."""

    code: SportCode
    display_name: str
    match_lifecycle: MatchLifecycleRules
    roster_rules: RosterRules
    match_event_catalog: MatchEventTypeCatalog
    team_statistic_schema: StatisticSchema
    player_statistic_schema: StatisticSchema
    player_positions: frozenset[str]


class SportPluginRegistryPort(Protocol):
    def register(self, plugin: SportPlugin) -> None: ...
    def get(self, code: SportCode) -> SportPlugin: ...
    def all(self) -> tuple[SportPlugin, ...]: ...
