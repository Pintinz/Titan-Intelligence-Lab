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
from modules.sports.domain.value_objects import FixtureStatus, TeamId
from modules.sports.ports.repositories import FixtureRepositoryPort, TeamStatisticsRepositoryPort

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


@dataclass
class FixtureFormDifferentialCalculator:
    """The "form vs. opponent" margin feature this module's docstring flagged as a documented
    future addition — a cross-team join within a match, registered under EntityType.FIXTURE
    rather than EntityType.TEAM. `PredictionContextBuilder` resolves every mapped feature
    against the exact entity_type/entity_id the prediction request itself was made for, so a
    fixture-level market (e.g. football.match_result) can only ever see fixture-scoped features
    — a team's own rolling form, however well populated, is invisible to it without this join.
    """

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
                f"{self.sport_code.replace('_', ' ').title()} Form Differential — {self.stat_key} (last {self.window})",
                f"Home team's rolling '{self.stat_key}' average minus the away team's, each over "
                f"their own last {self.window} matches.",
                self.sport_code,
                FeatureCategory.ENGINEERED,
                formula=f"mean_home({self.stat_key}, last {self.window}) - mean_away({self.stat_key}, last {self.window})",
                data_type=FeatureDataType.FLOAT,
                owner=SYSTEM_REVIEWER,
                entity_type=EntityType.FIXTURE,
            )
        except FeatureAlreadyRegisteredError:
            return
        await self.registration.submit_for_review(self.feature_key)
        await self.registration.approve(self.feature_key, SYSTEM_REVIEWER, now)

    async def _team_average(self, team_id: TeamId, now: datetime) -> float | None:
        recent = await self.statistics.list_recent_by_team(team_id, before=now, limit=self.window)
        values = [float(s.stat_set[self.stat_key]) for s in recent if _is_number(s.stat_set.get(self.stat_key))]
        if not values:
            return None
        return sum(values) / len(values)

    async def compute_and_write(
        self, fixture_id: str, home_team_id: TeamId, away_team_id: TeamId, now: datetime
    ) -> FeatureValue | None:
        home_average = await self._team_average(home_team_id, now)
        away_average = await self._team_average(away_team_id, now)
        if home_average is None or away_average is None:
            return None
        return await self.store.write(self.feature_key, EntityType.FIXTURE, fixture_id, home_average - away_average, now)


@dataclass
class FixtureExpectedGoalsCalculator:
    """Each side's expected-goals rate for a fixture (audit fix 2026-08-02, built for
    `football.correct_score`) — the home team's average goals scored across its own last
    ``window`` completed matches, and the away team's, independently (not a differential like
    `FixtureFormDifferentialCalculator` — a Poisson scoreline model needs each side's own rate).

    Reads real historical results from `Fixture.home_score`/`away_score`
    (`FixtureRepositoryPort.list_recent_by_team`), not `TeamStatistics` — this module's own
    docstring notes football's `TeamStatistics.stat_set` has no goals-scored field at all; goals
    only exist on the `Fixture` entity itself, recorded once a match completes.
    """

    registration: FeatureRegistrationService
    store: FeatureStoreService
    fixtures: FixtureRepositoryPort
    sport_code: str
    home_feature_key: str
    away_feature_key: str
    window: int = 10

    async def ensure_registered(self, now: datetime) -> None:
        """Idempotent — registers and approves both features if they don't already exist. Safe
        to call on every engineering run/startup."""
        for feature_key, side in ((self.home_feature_key, "home"), (self.away_feature_key, "away")):
            existing = await self.registration.definitions.get(FeatureKey(feature_key))
            if existing is not None:
                continue
            try:
                await self.registration.register(
                    feature_key,
                    f"{self.sport_code.replace('_', ' ').title()} Expected Goals — {side.title()} "
                    f"(last {self.window} completed matches)",
                    f"Average goals scored by the {side} team across its own last {self.window} "
                    "completed matches, regardless of venue.",
                    self.sport_code,
                    FeatureCategory.ENGINEERED,
                    formula=f"mean(goals_scored) over the {side} team's last {self.window} completed matches",
                    data_type=FeatureDataType.FLOAT,
                    owner=SYSTEM_REVIEWER,
                    entity_type=EntityType.FIXTURE,
                )
            except FeatureAlreadyRegisteredError:
                continue
            await self.registration.submit_for_review(feature_key)
            await self.registration.approve(feature_key, SYSTEM_REVIEWER, now)

    async def _team_average_goals_scored(self, team_id: TeamId, now: datetime) -> float | None:
        recent = await self.fixtures.list_recent_by_team(team_id, before=now, limit=self.window * 3)
        scored: list[int] = []
        for fixture in recent:
            if fixture.status is not FixtureStatus.COMPLETED:
                continue
            if fixture.home_score is None or fixture.away_score is None:
                continue
            if fixture.home_team_id == team_id:
                scored.append(fixture.home_score)
            elif fixture.away_team_id == team_id:
                scored.append(fixture.away_score)
            if len(scored) >= self.window:
                break
        if not scored:
            return None
        return sum(scored) / len(scored)

    async def compute_and_write(
        self, fixture_id: str, home_team_id: TeamId, away_team_id: TeamId, now: datetime
    ) -> tuple[FeatureValue | None, FeatureValue | None]:
        home_average = await self._team_average_goals_scored(home_team_id, now)
        away_average = await self._team_average_goals_scored(away_team_id, now)
        home_value = (
            await self.store.write(self.home_feature_key, EntityType.FIXTURE, fixture_id, home_average, now)
            if home_average is not None else None
        )
        away_value = (
            await self.store.write(self.away_feature_key, EntityType.FIXTURE, fixture_id, away_average, now)
            if away_average is not None else None
        )
        return home_value, away_value


def football_fixture_expected_goals_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    fixtures: FixtureRepositoryPort,
    window: int = 10,
) -> FixtureExpectedGoalsCalculator:
    return FixtureExpectedGoalsCalculator(
        registration=registration,
        store=store,
        fixtures=fixtures,
        sport_code="football",
        home_feature_key="football.fixture.expected_home_goals",
        away_feature_key="football.fixture.expected_away_goals",
        window=window,
    )


def _football_stat_differential_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    stat_key: str,
    window: int = 5,
) -> FixtureFormDifferentialCalculator:
    return FixtureFormDifferentialCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="football",
        feature_key=f"football.fixture.form_{stat_key}_diff_last{window}",
        stat_key=stat_key,
        window=window,
    )


def football_fixture_form_differential_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> FixtureFormDifferentialCalculator:
    """The original (Milestone 9.2 audit-fix) shots_on_target differential — kept as its own
    entry point since it's what every market's `required_features` already names and every
    existing caller/test still passes around as a single calculator. New stat differentials
    (2026-08-03) are additive, via `football_fixture_stat_differential_calculators` below, not a
    replacement for this."""
    return _football_stat_differential_calculator(registration, store, statistics, stat_key="shots_on_target", window=window)


# The four `TeamStatistics.stat_set` fields API-Football already syncs per fixture
# (`ApiFootballAdapter._STAT_TYPE_MAP`) but which, until now, no feature or market ever consumed
# — plus cards, which the same map only just started syncing at all (2026-08-03 audit: the raw
# provider payload always included yellow/red cards, `_STAT_TYPE_MAP` just silently dropped them).
_ADDITIONAL_FOOTBALL_STAT_KEYS: tuple[str, ...] = ("possession_pct", "shots_total", "corners", "fouls", "cards_yellow")


def football_fixture_stat_differential_calculators(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> tuple[FixtureFormDifferentialCalculator, ...]:
    """Every football fixture-level stat-differential feature this platform computes today, as one
    tuple — the original shots_on_target calculator plus one per `_ADDITIONAL_FOOTBALL_STAT_KEYS`
    entry, all built the same generic way. `EntityReconciliationService.form_differential_calculators`
    takes the whole tuple so every stat gets (re)computed on every football fixture reconciliation,
    not just shots_on_target."""
    return tuple(
        _football_stat_differential_calculator(registration, store, statistics, stat_key=key, window=window)
        for key in ("shots_on_target", *_ADDITIONAL_FOOTBALL_STAT_KEYS)
    )


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
