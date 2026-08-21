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

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.features.application.feature_registration_service import (
    FeatureAlreadyRegisteredError,
    FeatureRegistrationService,
)
from modules.features.application.feature_store_service import FeatureStoreService
from modules.features.domain.entities import FeatureValue
from modules.features.domain.value_objects import EntityType, FeatureCategory, FeatureDataType, FeatureKey
from modules.sports.domain.entities import Lineup, Transfer
from modules.sports.domain.value_objects import FixtureStatus, TeamId
from modules.sports.ports.repositories import (
    FixtureRepositoryPort,
    LineupRepositoryPort,
    TeamStatisticsRepositoryPort,
    TransferRepositoryPort,
)

SYSTEM_REVIEWER = "prediction-platform"

# These features only change when `compute_and_write` runs — once per fixture reconciliation
# cycle for the entity involved, not continuously — so the registry default of 3600s (built for
# live/streaming data) wrongly read a normal few-hours-to-a-day gap between reconciliation runs
# as "completely stale," capping every prediction's confidence composite regardless of actual
# data quality. 24h matches a conservative "needs at least a daily refresh" expectation without
# claiming freshness the data doesn't have.
ENGINEERED_FEATURE_TTL_SECONDS = 24 * 3600

# Milestone 7 — how far back a confirmed transfer still counts as "recent squad churn" for
# `TransferActivityCalculator`. Not "the" correct value — a configured, documented default a
# future operator can retune without a code change, same posture as
# `modules.ingestion.application.provenance.LINEUP_PREMATCH_WINDOW_MINUTES`. 30 days covers a
# typical late-window signing's first few fixtures, where squad-integration effects are
# conventionally understood to matter most; older transfers are treated as already absorbed into
# the team's regular rolling form rather than "recent activity."
TRANSFER_ACTIVITY_WINDOW_DAYS = int(os.environ.get("TITANIQ_TRANSFER_ACTIVITY_WINDOW_DAYS") or 30)


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as modules.ingestion.application.sync_orchestrator._ensure_aware /
    data_quality_engine._ensure_aware — SQLite/aiosqlite drops tzinfo on read-back
    (docs/decisions.md ADR-007); a naive value is assumed UTC and stamped to match
    ``reference``'s awareness before comparison."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


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
                online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
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
                online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
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
                    online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
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


@dataclass
class LineupContinuityCalculator:
    """Milestone 6 — the first real structured-intelligence feature to consume Milestone 5's
    point-in-time-safe `Lineup.availability_classification`. A pure ratio (no hand-picked weight,
    same posture as every other calculator in this module — see market_seeding.py's own comment
    on why fabricated weights are avoided here): the fraction of a team's previous confirmed
    starting eleven that starts again in the lineup being reconciled right now.

    Deliberately computed ONLY when the lineup just reconciled is itself `VERIFIED_PRE_MATCH` —
    called from `EntityReconciliationService.reconcile_lineup` right after that classification is
    made, never from a lineup with unknown/post-match provenance (that would either leak
    post-match information or write a feature value with no honest `information_available_at` of
    its own to point to). The comparison baseline (the team's previous lineup) does not need the
    same guarantee — it's already a settled historical fact by the time this fixture is being
    predicted, not something that could leak the *current* fixture's outcome.

    Two independent features (home/away), not one differential — a team's own rotation affects
    its own output regardless of what the opponent did, so collapsing both sides into a single
    `home - away` number (the shape `FixtureFormDifferentialCalculator` uses) would assume a
    symmetric relationship this signal doesn't actually have. Matches
    `FixtureExpectedGoalsCalculator`'s independent-home/away-value shape instead."""

    registration: FeatureRegistrationService
    store: FeatureStoreService
    lineups: LineupRepositoryPort
    sport_code: str
    feature_key: str

    async def ensure_registered(self, now: datetime) -> None:
        existing = await self.registration.definitions.get(FeatureKey(self.feature_key))
        if existing is not None:
            return
        try:
            await self.registration.register(
                self.feature_key,
                f"{self.sport_code.replace('_', ' ').title()} Lineup Continuity",
                "Fraction of this team's previous confirmed starting lineup that starts again in "
                "the confirmed lineup for this fixture (1.0 = unchanged eleven, 0.0 = entirely "
                "different). Only computed once this fixture's own lineup is verified pre-match.",
                self.sport_code,
                FeatureCategory.ENGINEERED,
                formula="|current_starters ∩ previous_starters| / |previous_starters|",
                data_type=FeatureDataType.FLOAT,
                owner=SYSTEM_REVIEWER,
                entity_type=EntityType.FIXTURE,
                online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
            )
        except FeatureAlreadyRegisteredError:
            return
        await self.registration.submit_for_review(self.feature_key)
        await self.registration.approve(self.feature_key, SYSTEM_REVIEWER, now)
        # Milestone 4 leakage classification: this feature is only ever written from a
        # VERIFIED_PRE_MATCH lineup (see class docstring), so it earns PRE_MATCH_SAFE — set
        # directly on the freshly-registered definition since `register()` has no such parameter.
        definition = await self.registration.definitions.get(FeatureKey(self.feature_key))
        if definition is not None:
            definition.leakage_classification = "PRE_MATCH_SAFE"
            await self.registration.definitions.upsert(definition)

    @staticmethod
    def _continuity_ratio(current: Lineup, previous: Lineup | None) -> float | None:
        if previous is None:
            return None
        previous_starters = {s.player_id for s in previous.starters()}
        if not previous_starters:
            return None
        current_starters = {s.player_id for s in current.starters()}
        return len(current_starters & previous_starters) / len(previous_starters)

    async def compute_and_write(self, fixture_id: str, team_id: TeamId, lineup: Lineup, now: datetime) -> FeatureValue | None:
        if lineup.availability_classification != "VERIFIED_PRE_MATCH":
            return None
        before = lineup.information_available_at or now
        previous_candidates = await self.lineups.list_recent_by_team(team_id, before=before, limit=1)
        previous = previous_candidates[0] if previous_candidates else None
        ratio = self._continuity_ratio(lineup, previous)
        if ratio is None:
            return None
        return await self.store.write(self.feature_key, EntityType.FIXTURE, fixture_id, ratio, now)


def football_lineup_continuity_calculators(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    lineups: LineupRepositoryPort,
) -> tuple[LineupContinuityCalculator, LineupContinuityCalculator]:
    """Two independent calculators (home/away), same feature-key naming convention as
    `FixtureExpectedGoalsCalculator`'s `home_feature_key`/`away_feature_key` split — both write
    against `EntityType.FIXTURE`, distinguished by feature key, not by a side parameter, since
    `compute_and_write` is called once per (fixture, team) reconciliation, never for both sides
    at once (unlike the fixture-joined differential calculators above, which need both team ids
    simultaneously)."""
    home = LineupContinuityCalculator(
        registration=registration, store=store, lineups=lineups, sport_code="football",
        feature_key="football.fixture.home_lineup_continuity",
    )
    away = LineupContinuityCalculator(
        registration=registration, store=store, lineups=lineups, sport_code="football",
        feature_key="football.fixture.away_lineup_continuity",
    )
    return home, away


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


@dataclass
class TransferActivityCalculator:
    """Milestone 7 — the transfer-side counterpart to `LineupContinuityCalculator`, the second
    half of Milestone 5's "now genuinely unblocked" recommendation (lineups + transfers; injuries
    remain honestly blocked — no provider supplies a real report timestamp for them). Counts a
    team's confirmed transfers (incoming and outgoing) whose own record provenance is
    `VERIFIED_PRE_MATCH` and whose `effective_date` falls within `window_days` before the
    reconciliation time — a real, unweighted squad-churn count, not a fabricated or hand-tuned
    signal.

    Two independent features (home/away), not a differential — a team's own transfer activity
    affects only its own squad, not the opponent's, matching `LineupContinuityCalculator`'s
    reasoning exactly (see that class's docstring).

    Null semantics matter here in a way they don't for lineup continuity: a count of zero is only
    written when the team has at least one `VERIFIED_PRE_MATCH` transfer record on file at all —
    proof this team's transfer history has genuine pre-match verification coverage. A team with
    NO verified transfer records anywhere returns `None` (unavailable), never a fabricated zero
    that would silently read as "no squad churn" when the truth is "no verified visibility" — the
    exact "must remain unavailable/UNKNOWN rather than being fabricated" rule this milestone is
    governed by."""

    registration: FeatureRegistrationService
    store: FeatureStoreService
    transfers: TransferRepositoryPort
    sport_code: str
    feature_key: str
    window_days: int = TRANSFER_ACTIVITY_WINDOW_DAYS

    async def ensure_registered(self, now: datetime) -> None:
        existing = await self.registration.definitions.get(FeatureKey(self.feature_key))
        if existing is not None:
            return
        try:
            await self.registration.register(
                self.feature_key,
                f"{self.sport_code.replace('_', ' ').title()} Squad Transfer Activity",
                "Count of this team's confirmed incoming and outgoing transfers, effective within "
                f"the last {self.window_days} days, whose provenance is verified pre-match. "
                "Unavailable (not zero) when no verified transfer history exists for this team.",
                self.sport_code,
                FeatureCategory.ENGINEERED,
                formula=(
                    f"count(transfers where availability_classification == VERIFIED_PRE_MATCH "
                    f"and effective_date in [now - {self.window_days}d, now))"
                ),
                data_type=FeatureDataType.FLOAT,
                owner=SYSTEM_REVIEWER,
                entity_type=EntityType.FIXTURE,
                online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
            )
        except FeatureAlreadyRegisteredError:
            return
        await self.registration.submit_for_review(self.feature_key)
        await self.registration.approve(self.feature_key, SYSTEM_REVIEWER, now)
        # Milestone 4 leakage classification: this feature only ever counts VERIFIED_PRE_MATCH
        # transfer records (see class docstring), so it earns PRE_MATCH_SAFE — set directly on
        # the freshly-registered definition since `register()` has no such parameter.
        definition = await self.registration.definitions.get(FeatureKey(self.feature_key))
        if definition is not None:
            definition.leakage_classification = "PRE_MATCH_SAFE"
            await self.registration.definitions.upsert(definition)

    def _count_recent_verified(self, records: list[Transfer], now: datetime) -> float | None:
        verified = [r for r in records if r.availability_classification == "VERIFIED_PRE_MATCH"]
        if not verified:
            return None
        window_start = now - timedelta(days=self.window_days)
        count = sum(
            1 for r in verified
            if window_start <= _ensure_aware(r.effective_date, now) < now
        )
        return float(count)

    async def compute_and_write(self, fixture_id: str, team_id: TeamId, now: datetime) -> FeatureValue | None:
        records = await self.transfers.list_by_team(team_id)
        count = self._count_recent_verified(records, now)
        if count is None:
            return None
        return await self.store.write(self.feature_key, EntityType.FIXTURE, fixture_id, count, now)


def football_transfer_activity_calculators(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    transfers: TransferRepositoryPort,
) -> tuple[TransferActivityCalculator, TransferActivityCalculator]:
    """Two independent calculators (home/away), same shape as
    `football_lineup_continuity_calculators` — both write against `EntityType.FIXTURE`,
    distinguished by feature key."""
    home = TransferActivityCalculator(
        registration=registration, store=store, transfers=transfers, sport_code="football",
        feature_key="football.fixture.home_transfer_activity",
    )
    away = TransferActivityCalculator(
        registration=registration, store=store, transfers=transfers, sport_code="football",
        feature_key="football.fixture.away_transfer_activity",
    )
    return home, away


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


def basketball_fixture_form_differential_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> FixtureFormDifferentialCalculator:
    """POST-M24 Phase 5A — basketball's fixture-scoped analog of
    `football_fixture_form_differential_calculator`. `basketball.team.form_points_last5`
    (`basketball_form_calculator` above) is `EntityType.TEAM`-scoped and, per
    `FixtureFormDifferentialCalculator`'s own docstring, structurally invisible to a
    fixture-scoped market prediction request — exactly the gap football's own
    `required_features` fix (`FixtureFormDifferentialCalculator` for football) already closed.
    This is that same fix, reused verbatim for basketball, not a new mechanism."""
    return FixtureFormDifferentialCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="basketball",
        feature_key=f"basketball.fixture.form_points_diff_last{window}",
        stat_key="points",
        window=window,
    )


def baseball_fixture_form_differential_calculator(
    registration: FeatureRegistrationService,
    store: FeatureStoreService,
    statistics: TeamStatisticsRepositoryPort,
    window: int = 5,
) -> FixtureFormDifferentialCalculator:
    """POST-M24 Phase 5A — baseball's fixture-scoped analog, same reasoning as
    `basketball_fixture_form_differential_calculator` above."""
    return FixtureFormDifferentialCalculator(
        registration=registration,
        store=store,
        statistics=statistics,
        sport_code="baseball",
        feature_key=f"baseball.fixture.form_runs_diff_last{window}",
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
