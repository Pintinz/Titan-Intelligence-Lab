"""Application service orchestrating fixture status transitions and match-event recording
against the owning sport plugin's rules — the only place that connects "which sport is this"
to "what event types/transitions are legal" (docs/architecture.md §3, §4).
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.sports.domain.entities import Fixture, MatchEvent
from modules.sports.domain.value_objects import FixtureStatus, SportCode
from modules.sports.ports.plugin_registry import SportPluginRegistryPort
from modules.sports.ports.repositories import FixtureRepositoryPort


class UnrecognizedMatchEventError(ValueError):
    pass


@dataclass
class FixtureLifecycleService:
    fixtures: FixtureRepositoryPort
    plugins: SportPluginRegistryPort

    async def transition_fixture(
        self, fixture: Fixture, target: FixtureStatus
    ) -> Fixture:
        updated = fixture.transition_to(target)
        return await self.fixtures.upsert(updated)

    def validate_match_event(self, sport_code: SportCode, event: MatchEvent) -> None:
        plugin = self.plugins.get(sport_code)
        if not plugin.match_event_catalog.is_recognized(event.event_type):
            raise UnrecognizedMatchEventError(
                f"'{event.event_type}' is not a recognized event type for {sport_code}"
            )
