"""Windowed Feature Engineering (Milestone 9 task #137): features that need a rolling window of
past matches — team form — and so can't be computed from a single ``clean_record`` the way
task #136's `FeatureCalculatorPort` implementations are. These compute directly from
`TeamStatisticsRepositoryPort.list_recent_by_team()` (the additive windowed-history query this
milestone added to modules.sports, task #122) and write straight to the Feature Store via
`FeatureStoreService.write()` — the same direct-compute-then-write shape Milestone 8's
`FeatureStoreEnrichmentService` already established, not a `FeatureCalculatorPort` registration
(that pipeline is single-record only).

`RollingTeamStatAverageCalculator` is one generic, sport-agnostic engine: the rolling average of
one declared `TeamStatistics.stat_set` numeric field over a team's last N matches is
self-contained (no opponent join needed), so it's the exact same computation for every sport —
only *which* field differs. Each sport plugin (modules.sports.<sport>.plugin) declares its own
``team_statistic_schema`` with different field names — football tracks `shots_on_target` but has
no goals-scored field at all, basketball tracks `points`, baseball tracks `runs`, table tennis
tracks `points_won` — so this engine is parametrized by ``stat_key`` rather than assuming a
universal scoring field that doesn't exist in every schema (verified against each plugin's
declared `TEAM_STATISTIC_SCHEMA` before picking these keys).

Scope note (docs/decisions.md ADR pattern, same posture as Milestone 7's Similarity Engine and
Milestone 8's Feature Store Enrichment): one representative windowed feature per sport, proving
the mechanism end-to-end — a "form vs. opponent" margin feature (cross-team join within a match)
is a documented future addition against this same framework, not built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureRegistrationService,
)
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.sports.domain.value_objects import TeamId
from modules.sports.ports.repositories import TeamStatisticsRepositoryPort

SYSTEM_REVIEWER = "prediction-platform"


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass
class RollingTeamStatAverageCalculator:
    registration: FeatureRegistrationService
    store: FeatureStoreService
    statistics: TeamStatisticsRepositoryPort
    sport_code: str
    feature_key: str
    stat_key: str
    window: int = 5

    async def ensure_registered(self, now: datetime) -> None:
        """Idempotent — registers and approves this calculator's feature if it doesn't already
        exist. Safe to call on every engineering run/startup."""
        existing = await self.registration.definitions.get(FeatureKey(self.feature_key))
        if existing is not None:
            return
        try:
            await self.registration.register(
                self.feature_key,
                f"{self.sport_code.replace('_', ' ').title()} Team Form — {self.stat_key} (last {self.window})",
                f"Rolling average of '{self.stat_key}' across the team's last {self.window} matches.",
                self.sport_code,
                FeatureCategory.ENGINEERED,
                formula=f"mean({self.stat_key}) over last {self.window} matches",
                data_type=FeatureDataType.FLOAT,
                owner=SYSTEM_REVIEWER,
                entity_type=EntityType.TEAM,
            )
        except FeatureAlreadyRegisteredError:
            return
        await self.registration.submit_for_review(self.feature_key)
        await self.registration.approve(self.feature_key, SYSTEM_REVIEWER, now)

    async def compute_and_write(self, team_id: TeamId, now: datetime) -> FeatureValue | None:
        recent = await self.statistics.list_recent_by_team(team_id, before=now, limit=self.window)
        values = [float(s.stat_set[self.stat_key]) for s in recent if _is_number(s.stat_set.get(self.stat_key))]
        if not values:
            return None
        average = sum(values) / len(values)
        return await self.store.write(self.feature_key, EntityType.TEAM, str(team_id.value), average, now)


def football_form_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> RollingTeamStatAverageCalculator:
    return RollingTeamStatAverageCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="football",
        feature_key=f"football.team.form_shots_on_target_last{window}",
        stat_key="shots_on_target",
        window=window,
    )


def basketball_form_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> RollingTeamStatAverageCalculator:
    return RollingTeamStatAverageCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="basketball",
        feature_key=f"basketball.team.form_points_last{window}",
        stat_key="points",
        window=window,
    )


def baseball_form_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> RollingTeamStatAverageCalculator:
    return RollingTeamStatAverageCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="baseball",
        feature_key=f"baseball.team.form_runs_last{window}",
        stat_key="runs",
        window=window,
    )


def table_tennis_form_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> RollingTeamStatAverageCalculator:
    return RollingTeamStatAverageCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="table_tennis",
        feature_key=f"table_tennis.team.form_points_won_last{window}",
        stat_key="points_won",
        window=window,
    )
