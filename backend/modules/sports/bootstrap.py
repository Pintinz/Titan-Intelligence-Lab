"""Composition root for the sports module — the one place that imports every sport package
directly. apps/api and apps/worker call build_sport_plugin_registry() at startup; no other
module code imports modules.sports.football/basketball/baseball/table_tennis directly
(docs/architecture.md §4).
"""

from __future__ import annotations

from modules.sports.application.plugin_registry import SportPluginRegistry
from modules.sports.baseball.plugin import PLUGIN as BASEBALL_PLUGIN
from modules.sports.basketball.plugin import PLUGIN as BASKETBALL_PLUGIN
from modules.sports.football.plugin import PLUGIN as FOOTBALL_PLUGIN
from modules.sports.table_tennis.plugin import PLUGIN as TABLE_TENNIS_PLUGIN


def build_sport_plugin_registry() -> SportPluginRegistry:
    registry = SportPluginRegistry()
    for plugin in (FOOTBALL_PLUGIN, BASKETBALL_PLUGIN, BASEBALL_PLUGIN, TABLE_TENNIS_PLUGIN):
        registry.register(plugin)
    return registry
