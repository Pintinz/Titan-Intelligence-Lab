"""Milestone 13 — Mode 2 (historical/reconstruction) news relevance, a sibling to Mode 1's
`NewsRelevanceFilter`/`build_fixture_relevance_vocabulary` (Milestone 10), never a modification of
them. Mode 1 answers "is this article worth a Gemini call, given fixtures currently upcoming";
Mode 2 answers a structurally different question — "given a specific historical fixture and a
specific historical reference time, was this already-extracted event's entity actually associated
with that fixture at that time" — and must never reach for "currently upcoming" or "currently
associated" data to answer it. See `historical_entity_resolution_service.py` for why current
`Player.team_id` and current Knowledge Graph `PLAYS_FOR` edges are both explicitly excluded from
this reasoning.

This engine does not perform entity extraction/NER — that remains
`EntityExtractionService`/`EntityResolutionService`'s job (Milestone 8/9, reused as-is). It
consumes an already-extracted `NewsEvent`'s `resolved_entities` (Knowledge Graph node refs) and
asks, for each one, whether it was genuinely tied to the given historical fixture at the given
historical reference time.

``reference_time`` is always an explicit caller-supplied parameter (never read internally off
`NewsEvent.information_available_at`) — matching the milestone's own specified interface shape,
``resolve_relevance(article, reference_time, fixture_context)``. A caller wanting the honest
production default passes ``event.information_available_at`` (the Milestone 9 field, which
by construction only carries a genuine timestamp for the — currently nonexistent —
`VERIFIED_PRE_MATCH` case, correctly gating every `BACKFILL`/`ADMIN_MANUAL` event straight to
`INSUFFICIENT_PROVENANCE`, matching the milestone's own governing principle: "if this chain
cannot be proven, exclude from training"). ``None`` always means "no reference time is known" —
never fabricated.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from modules.intelligence.application.historical_entity_resolution_service import (
    HistoricalEntityResolutionService,
    PlayerMembershipStatus,
)
from modules.intelligence.domain.entities import NewsEvent
from modules.intelligence.domain.value_objects import EntityResolutionStatus, NewsEventType
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort
from modules.sports.domain.value_objects import FixtureId, PlayerId, TeamId

# Injected, never imported directly — `modules.intelligence` does not depend on
# `modules.predictions` (the same one-directional-boundary posture already documented for
# `modules.ingestion`). The real implementation (querying Milestone 9's
# `MARKET_IMPACT_RULES`) is composed in `apps/api/composition.py`, which already depends on both.
MarketRuleExistsPort = Callable[[NewsEventType, str], bool]


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


def _looks_like_node_id(ref: str) -> KGNodeId | None:
    try:
        return KGNodeId(UUID(ref))
    except ValueError:
        return None


class HistoricalRelevanceClassification(str, Enum):
    HISTORICALLY_RELEVANT = "historically_relevant"
    NOT_RELEVANT = "not_relevant"
    HISTORICALLY_UNRESOLVED = "historically_unresolved"
    ENTITY_UNRESOLVED = "entity_unresolved"
    MARKET_UNRESOLVED = "market_unresolved"
    INSUFFICIENT_PROVENANCE = "insufficient_provenance"


@dataclass(frozen=True)
class HistoricalFixtureContext:
    """The historical fixture's own recorded facts — never a team's current schedule, never
    "currently upcoming." A `Fixture` row already IS the point-in-time snapshot (spec §5/§7)."""

    fixture_id: FixtureId
    home_team_id: TeamId
    away_team_id: TeamId
    kickoff: datetime


@dataclass(frozen=True)
class HistoricalRelevanceResult:
    """Fully explainable (spec §17) — every conclusion traces to named evidence, never a bare
    boolean. `entity_resolution`/`membership_resolution`/`fixture_resolution`/`market_resolution`
    are independent, human-readable status strings, deliberately not booleans, so a caller can see
    *which* stage produced an unresolved/failed outcome without re-deriving it."""

    classification: HistoricalRelevanceClassification
    entity_resolution: str
    membership_resolution: str
    fixture_resolution: str
    market_resolution: str | None
    information_available_at: datetime | None
    reference_time: datetime | None
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class HistoricalNewsRelevanceEngine:
    kg_nodes: KGNodeRepositoryPort
    entity_resolution: HistoricalEntityResolutionService
    market_rule_exists: MarketRuleExistsPort | None = None

    async def resolve_relevance(
        self,
        event: NewsEvent,
        reference_time: datetime | None,
        fixture_context: HistoricalFixtureContext,
        *,
        market_key: str | None = None,
    ) -> HistoricalRelevanceResult:
        if reference_time is None:
            return HistoricalRelevanceResult(
                classification=HistoricalRelevanceClassification.INSUFFICIENT_PROVENANCE,
                entity_resolution="not_attempted", membership_resolution="not_attempted",
                fixture_resolution="not_attempted", market_resolution=None,
                information_available_at=event.information_available_at, reference_time=None,
                evidence=(
                    "reference_time is unknown — historical relevance cannot be established "
                    "without a known information-availability time; never fabricated",
                ),
            )

        reference_time = _ensure_aware(reference_time, fixture_context.kickoff)
        evidence: list[str] = [
            f"fixture.id={fixture_context.fixture_id.value} "
            f"home_team_id={fixture_context.home_team_id.value} away_team_id={fixture_context.away_team_id.value}"
        ]

        resolved_mentions = [
            mention for mention in event.resolved_entities if mention.status is EntityResolutionStatus.RESOLVED
        ]
        if not resolved_mentions:
            return HistoricalRelevanceResult(
                classification=HistoricalRelevanceClassification.ENTITY_UNRESOLVED,
                entity_resolution="unresolved", membership_resolution="not_attempted",
                fixture_resolution="resolved", market_resolution=None,
                information_available_at=event.information_available_at, reference_time=reference_time,
                evidence=tuple(evidence + ["event has no resolved entity mentions"]),
            )

        any_relevant = False
        any_unresolved_membership = False
        checked_any_entity = False

        for mention in resolved_mentions:
            node_id = _looks_like_node_id(mention.ref)
            if node_id is None:
                evidence.append(f"mention ref={mention.ref!r} is not a Knowledge Graph node id")
                continue
            node = await self.kg_nodes.get(node_id)
            if node is None:
                evidence.append(f"Knowledge Graph node {mention.ref} no longer exists")
                continue

            if node.node_type is NodeType.TEAM:
                checked_any_entity = True
                team_id = TeamId(UUID(node.entity_ref))
                if team_id == fixture_context.home_team_id:
                    any_relevant = True
                    evidence.append(f"team {team_id.value} matches fixture.home_team_id")
                elif team_id == fixture_context.away_team_id:
                    any_relevant = True
                    evidence.append(f"team {team_id.value} matches fixture.away_team_id")
                else:
                    evidence.append(f"team {team_id.value} does not match either fixture team")

            elif node.node_type is NodeType.PLAYER:
                checked_any_entity = True
                player_id = PlayerId(UUID(node.entity_ref))
                membership = await self.entity_resolution.resolve_player_membership(player_id, reference_time)
                evidence.append(f"player {player_id.value} historical membership: {membership.evidence}")
                if membership.status is PlayerMembershipStatus.HISTORICALLY_UNRESOLVED:
                    any_unresolved_membership = True
                    continue
                if membership.team_id is not None and membership.team_id in (
                    fixture_context.home_team_id, fixture_context.away_team_id,
                ):
                    any_relevant = True
                # else: resolved membership, but not this fixture's teams (or no club) — not an
                # error, simply not relevant via this entity.

        if not checked_any_entity:
            return HistoricalRelevanceResult(
                classification=HistoricalRelevanceClassification.ENTITY_UNRESOLVED,
                entity_resolution="unresolved", membership_resolution="not_attempted",
                fixture_resolution="resolved", market_resolution=None,
                information_available_at=event.information_available_at, reference_time=reference_time,
                evidence=tuple(evidence + ["no team/player entity could be resolved via the knowledge graph"]),
            )

        if any_relevant:
            classification = HistoricalRelevanceClassification.HISTORICALLY_RELEVANT
            membership_resolution = "resolved"
        elif any_unresolved_membership:
            classification = HistoricalRelevanceClassification.HISTORICALLY_UNRESOLVED
            membership_resolution = "unresolved"
        else:
            classification = HistoricalRelevanceClassification.NOT_RELEVANT
            membership_resolution = "resolved"

        market_resolution: str | None = None
        if market_key is not None and classification is HistoricalRelevanceClassification.HISTORICALLY_RELEVANT:
            if self.market_rule_exists is None:
                market_resolution = "unresolved"
                classification = HistoricalRelevanceClassification.MARKET_UNRESOLVED
                evidence.append("no market-rule checker configured — market relevance cannot be assumed")
            else:
                has_rule = self.market_rule_exists(event.event_type, market_key)
                market_resolution = "resolved" if has_rule else "unresolved"
                if not has_rule:
                    classification = HistoricalRelevanceClassification.MARKET_UNRESOLVED
                    evidence.append(
                        f"no MarketImpactRule exists for event_type={event.event_type.value} market_key={market_key!r}"
                    )

        return HistoricalRelevanceResult(
            classification=classification,
            entity_resolution="resolved",
            membership_resolution=membership_resolution,
            fixture_resolution="resolved",
            market_resolution=market_resolution,
            information_available_at=event.information_available_at,
            reference_time=reference_time,
            evidence=tuple(evidence),
        )
