"""In-memory SportPluginRegistry — no I/O, so it lives in the application layer rather than
infrastructure. Composed once at process startup (apps/api, apps/worker) with every sport
plugin registered; nothing else in the codebase imports a sport package directly.
"""

from __future__ import annotations

from modules.sports.domain.value_objects import SportCode
from modules.sports.ports.plugin_registry import SportPlugin


class UnknownSportError(KeyError):
    pass


class SportPluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[SportCode, SportPlugin] = {}

    def register(self, plugin: SportPlugin) -> None:
        if plugin.code in self._plugins:
            raise ValueError(f"sport plugin already registered for {plugin.code}")
        self._plugins[plugin.code] = plugin

    def get(self, code: SportCode) -> SportPlugin:
        try:
            return self._plugins[code]
        except KeyError as exc:
            raise UnknownSportError(f"no plugin registered for sport '{code}'") from exc

    def all(self) -> tuple[SportPlugin, ...]:
        return tuple(self._plugins.values())
