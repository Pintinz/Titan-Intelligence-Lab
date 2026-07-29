import pytest

from modules.sports.application.plugin_registry import SportPluginRegistry, UnknownSportError
from modules.sports.baseball.plugin import PLUGIN as BASEBALL_PLUGIN
from modules.sports.basketball.plugin import PLUGIN as BASKETBALL_PLUGIN
from modules.sports.bootstrap import build_sport_plugin_registry
from modules.sports.domain.value_objects import SportCode
from modules.sports.football.plugin import PLUGIN as FOOTBALL_PLUGIN
from modules.sports.table_tennis.plugin import PLUGIN as TABLE_TENNIS_PLUGIN

ALL_PLUGINS = (FOOTBALL_PLUGIN, BASKETBALL_PLUGIN, BASEBALL_PLUGIN, TABLE_TENNIS_PLUGIN)


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=lambda p: p.code.value)
def test_plugin_declares_a_non_empty_event_catalog(plugin):
    assert len(plugin.match_event_catalog.event_types) > 0


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=lambda p: p.code.value)
def test_plugin_statistic_schemas_are_non_empty(plugin):
    assert len(plugin.team_statistic_schema.fields) > 0
    assert len(plugin.player_statistic_schema.fields) > 0


@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=lambda p: p.code.value)
def test_plugin_roster_rules_are_internally_consistent(plugin):
    assert plugin.roster_rules.min_on_field <= plugin.roster_rules.max_on_field


def test_registry_resolves_every_registered_sport(plugin_registry):
    for code in SportCode:
        plugin = plugin_registry.get(code)
        assert plugin.code is code


def test_registry_raises_for_unregistered_sport():
    registry = SportPluginRegistry()

    with pytest.raises(UnknownSportError):
        registry.get(SportCode.FOOTBALL)


def test_registry_rejects_duplicate_registration():
    registry = SportPluginRegistry()
    registry.register(FOOTBALL_PLUGIN)

    with pytest.raises(ValueError):
        registry.register(FOOTBALL_PLUGIN)


def test_bootstrap_registers_all_four_phase_one_sports():
    registry = build_sport_plugin_registry()

    codes = {plugin.code for plugin in registry.all()}

    assert codes == {
        SportCode.FOOTBALL,
        SportCode.BASKETBALL,
        SportCode.BASEBALL,
        SportCode.TABLE_TENNIS,
    }
