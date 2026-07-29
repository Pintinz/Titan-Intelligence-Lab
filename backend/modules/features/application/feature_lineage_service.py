"""Feature lineage validation — every dependency must already be a registered feature (no
forward references), and adding a dependency edge must never create a cycle. Both are leakage
guardrails as much as graph-integrity ones: a feature that could depend on itself transitively,
or on something not yet defined, is exactly the shape a data-leakage bug takes
(docs/feature_catalog.md §2 "Never create features that cannot be validated")."""

from __future__ import annotations

from dataclasses import dataclass

from modules.features.domain.entities import FeatureLineageEdge
from modules.features.domain.value_objects import FeatureKey
from modules.features.ports.repositories import FeatureDefinitionRepositoryPort, FeatureLineageRepositoryPort


@dataclass
class FeatureLineageService:
    lineage: FeatureLineageRepositoryPort
    definitions: FeatureDefinitionRepositoryPort

    async def validate_dependencies(
        self, feature_key: FeatureKey, dependencies: tuple[FeatureKey, ...]
    ) -> list[str]:
        errors: list[str] = []
        for dep in dependencies:
            if dep == feature_key:
                errors.append(f"'{feature_key}' cannot depend on itself")
                continue
            if await self.definitions.get(dep) is None:
                errors.append(f"dependency '{dep}' is not a registered feature")
        if errors:
            return errors  # cycle-check below assumes every dep resolves; don't compound errors

        for dep in dependencies:
            if await self._can_reach(dep, feature_key, set()):
                errors.append(
                    f"registering '{dep}' as a dependency of '{feature_key}' would create a cycle"
                )
        return errors

    async def _can_reach(self, start: FeatureKey, target: FeatureKey, visited: set[FeatureKey]) -> bool:
        if start == target:
            return True
        if start in visited:
            return False
        visited.add(start)
        for dep in await self.lineage.list_dependencies(start):
            if await self._can_reach(dep, target, visited):
                return True
        return False

    async def record_dependencies(self, feature_key: FeatureKey, dependencies: tuple[FeatureKey, ...]) -> None:
        for dep in dependencies:
            await self.lineage.add_edge(FeatureLineageEdge(feature_key=feature_key, depends_on_feature_key=dep))

    async def dependency_closure(self, feature_key: FeatureKey) -> set[FeatureKey]:
        """Every feature this one transitively depends on — used for impact analysis before
        deprecating a feature (docs/feature_catalog.md §1 "Models Using Feature")."""
        closure: set[FeatureKey] = set()

        async def _walk(key: FeatureKey) -> None:
            for dep in await self.lineage.list_dependencies(key):
                if dep not in closure:
                    closure.add(dep)
                    await _walk(dep)

        await _walk(feature_key)
        return closure
