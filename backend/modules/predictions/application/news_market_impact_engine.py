"""Milestone 9 — News Market Impact Engine (spec §10): NEWS EVENT -> EVENT TYPE -> ENTITY/ROLE ->
MARKET -> IMPACT FUNCTION -> IMPACT VALUE -> CONFIDENCE ADJUSTMENT -> NEWS FEATURE.

Three market-specific feature dimensions per side (home/away), not one generic composite —
`goal_impact` (total-goals-style markets), `clean_sheet_impact` (clean-sheet markets),
`btts_impact` (both-teams-to-score) — populated only from `MARKET_IMPACT_RULES`
(`news_market_impact_registry.py`). Every contributing event must be `is_feature_eligible()`
(VERIFIED_PRE_MATCH + every entity resolved) AND still inside its rule's validity window at
*read* time, not just at the time it was originally classified — the same "re-check the window
at consumption, don't just trust a stale write-time classification" posture
`TransferActivityCalculator` already established (Milestone 7).

Null semantics mirror `TransferActivityCalculator` exactly: a dimension with zero relevant
feature-eligible events writes nothing (`None`, unavailable — not a fabricated zero); a dimension
where evidence exists but nets to zero (e.g. an injury and a recovery cancel out) writes a real
`0.0`.
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
from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
    PlayerMembershipStatus,
)
from modules.intelligence.application.news_provenance import (
    CONFIDENCE_WEIGHT_MULTIPLIERS,
    is_information_available_before_kickoff,
)
from modules.intelligence.domain.value_objects import NewsEventType
from modules.intelligence.ports.repositories import NewsEventRepositoryPort
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.predictions.application.news_market_impact_registry import MARKET_IMPACT_RULES, normalize_player_role
from modules.sports.domain.value_objects import PlayerId, TeamId
from modules.sports.ports.repositories import PlayerRepositoryPort, TransferRepositoryPort

SYSTEM_REVIEWER = "prediction-platform"
ENGINEERED_FEATURE_TTL_SECONDS = 24 * 3600

_FEATURE_DIMENSIONS: tuple[str, ...] = ("goal_impact", "clean_sheet_impact", "btts_impact")

_DIMENSION_DESCRIPTIONS: dict[str, str] = {
    "goal_impact": (
        "Signed, confidence-weighted news-derived adjustment to this team's expected goal "
        "output, from feature-eligible forward/striker injury, suspension, or recovery events "
        "affecting this team's roster."
    ),
    "clean_sheet_impact": (
        "Signed, confidence-weighted news-derived adjustment to this team's clean-sheet "
        "likelihood, from feature-eligible goalkeeper injury, suspension, or recovery events "
        "affecting this team's roster."
    ),
    "btts_impact": (
        "Signed, confidence-weighted news-derived adjustment to the likelihood both teams "
        "score, from feature-eligible forward and goalkeeper injury events affecting this "
        "team's roster."
    ),
}


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """Same fix as modules.ingestion.application.sync_orchestrator._ensure_aware and its two
    other duplicates — SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class NewsMarketImpactEngine:
    registration: FeatureRegistrationService
    store: FeatureStoreService
    events: NewsEventRepositoryPort
    kg_nodes: KGNodeRepositoryPort
    players: PlayerRepositoryPort
    sport_code: str = "football"
    # Milestone 14, optional/additive — every existing caller's construction is unchanged (both
    # default None), so live/current-fixture behavior is byte-identical to before. Required
    # together only when a caller passes `historical_reference_time` to `team_contributions`/
    # `compute_and_write` — see `_resolve_roster`'s fail-closed check below.
    transfers: TransferRepositoryPort | None = None
    historical_entity_resolution: HistoricalEntityResolutionService | None = None

    def feature_key(self, side: str, dimension: str) -> str:
        return f"news.{self.sport_code}.{side}_{dimension}"

    async def ensure_registered(self, now: datetime) -> None:
        for side in ("home", "away"):
            for dimension in _FEATURE_DIMENSIONS:
                feature_key = self.feature_key(side, dimension)
                existing = await self.registration.definitions.get(FeatureKey(feature_key))
                if existing is not None:
                    continue
                try:
                    await self.registration.register(
                        feature_key,
                        f"{self.sport_code.title()} News {dimension.replace('_', ' ').title()} ({side.title()})",
                        _DIMENSION_DESCRIPTIONS[dimension],
                        self.sport_code,
                        FeatureCategory.AI_EXTRACTED,
                        formula=(
                            "sum(direction * magnitude * confidence_weight for each feature-eligible, "
                            "still-valid MARKET_IMPACT_RULES match affecting this team's roster)"
                        ),
                        data_type=FeatureDataType.FLOAT,
                        owner=SYSTEM_REVIEWER,
                        entity_type=EntityType.FIXTURE,
                        online_ttl_seconds=ENGINEERED_FEATURE_TTL_SECONDS,
                        # Every contributing event is required to be is_feature_eligible()
                        # (VERIFIED_PRE_MATCH) before it can contribute anything.
                        leakage_classification="PRE_MATCH_SAFE",
                    )
                except FeatureAlreadyRegisteredError:
                    continue
                await self.registration.submit_for_review(feature_key)
                await self.registration.approve(feature_key, SYSTEM_REVIEWER, now)

    async def _resolve_roster(
        self, team_id: TeamId, historical_reference_time: datetime | None,
    ) -> list:
        """Milestone 14: the roster used to scan for news events. Live/current mode (the default,
        every pre-M14 caller's exact behavior) reads `players.list_by_team` unchanged — real, but
        only ever "who is on this team right now" — and returns the same `Player` objects that
        call already produced, with no new dependency on `players.get`.

        Historical mode (``historical_reference_time`` given) must NEVER read that same current
        roster — the Milestone 13 audit's own finding — so it is structurally routed through
        `HistoricalEntityResolutionService.resolve_player_membership` (Transfer.effective_date
        chains) instead. Candidates come from `transfers.list_by_team`, a real, bounded query;
        each candidate's membership is independently re-verified at `historical_reference_time`
        before being trusted, so a player who has since transferred away (or in) is correctly
        excluded (or included) based on genuine evidence, not current state. `players.get` is
        used only on this branch, to fetch the full `Player` record for a historically-resolved id.

        Fails closed, not silently: a caller passing `historical_reference_time` without also
        wiring `transfers`/`historical_entity_resolution` gets a clear error, never a silent
        fallback to current-roster reads (which would defeat the whole point)."""
        if historical_reference_time is None:
            return await self.players.list_by_team(team_id)

        if self.transfers is None or self.historical_entity_resolution is None:
            raise ValueError(
                "historical_reference_time was provided but this NewsMarketImpactEngine was "
                "constructed without `transfers`/`historical_entity_resolution` — refusing to "
                "silently fall back to current roster membership (Player.team_id)."
            )

        candidate_ids: set[PlayerId] = set()
        for transfer in await self.transfers.list_by_team(team_id):
            candidate_ids.add(transfer.player_id)

        resolved = []
        for player_id in candidate_ids:
            membership = await self.historical_entity_resolution.resolve_player_membership(
                player_id, historical_reference_time,
            )
            if membership.status is not PlayerMembershipStatus.HISTORICALLY_RESOLVED or membership.team_id != team_id:
                continue
            player = await self.players.get(player_id)
            if player is not None:
                resolved.append(player)
        return resolved

    async def team_contributions(
        self, team_id: TeamId, now: datetime, kickoff: datetime | None = None,
        historical_reference_time: datetime | None = None,
    ) -> dict[str, tuple[float, bool]]:
        """Returns {dimension: (net_value, has_any_evidence)} for one team — mirrors
        `TransferActivityCalculator._count_recent_verified`'s "genuine zero vs no evidence at
        all" split, generalized to three dimensions computed together in one roster scan.

        ``kickoff`` (Milestone 10, optional, additive — default ``None`` preserves every existing
        caller's exact prior behavior): when given the target fixture's own kickoff time, an
        event whose ``information_available_at`` is not strictly before it is excluded — the
        direct, fixture-specific enforcement of "never let post-kickoff information influence a
        pre-match prediction," on top of (not instead of) the event-type TTL window check below.

        ``historical_reference_time`` (Milestone 14, optional, additive — default ``None``
        preserves every existing caller's exact prior behavior): see `_resolve_roster`."""
        totals: dict[str, float] = {d: 0.0 for d in _FEATURE_DIMENSIONS}
        has_evidence: dict[str, bool] = {d: False for d in _FEATURE_DIMENSIONS}

        roster = await self._resolve_roster(team_id, historical_reference_time)
        for player in roster:
            role = normalize_player_role(player.position)
            if role is None:
                continue
            node = await self.kg_nodes.get_by_entity_ref(NodeType.PLAYER, str(player.id.value))
            if node is None:
                continue
            player_events = await self.events.list_for_entity(str(node.id))
            for event in player_events:
                if not event.is_feature_eligible():
                    continue
                if kickoff is not None and event.information_available_at is not None:
                    available_at = _ensure_aware(event.information_available_at, now)
                    if not is_information_available_before_kickoff(available_at, _ensure_aware(kickoff, now)):
                        continue
                for rule in MARKET_IMPACT_RULES:
                    if rule.event_type is not event.event_type or rule.entity_role != role:
                        continue
                    occurred_at = _ensure_aware(event.occurred_at, now)
                    age_hours = (now - occurred_at).total_seconds() / 3600
                    if age_hours < 0 or age_hours > rule.ttl_hours:
                        continue  # expired, or (defensively) an event dated after `now`
                    dimension = rule.feature_key_stem.rsplit(".", 1)[-1]
                    weight = CONFIDENCE_WEIGHT_MULTIPLIERS.get(event.confidence_tier, 0.0)
                    totals[dimension] += rule.direction * rule.magnitude * weight
                    has_evidence[dimension] = True

        return {d: (totals[d], has_evidence[d]) for d in _FEATURE_DIMENSIONS}

    async def compute_and_write(
        self, fixture_id: str, team_id: TeamId, side: str, now: datetime, kickoff: datetime | None = None,
        historical_reference_time: datetime | None = None,
    ) -> list[FeatureValue]:
        contributions = await self.team_contributions(team_id, now, kickoff, historical_reference_time)
        written: list[FeatureValue] = []
        for dimension, (value, has_evidence) in contributions.items():
            if not has_evidence:
                continue
            feature_key = self.feature_key(side, dimension)
            written.append(await self.store.write(feature_key, EntityType.FIXTURE, fixture_id, value, now))
        return written
