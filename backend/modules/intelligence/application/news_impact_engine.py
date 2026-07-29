"""News Impact Engine (Milestone 8 "NEWS IMPACT ENGINE": "Evaluate: Injury Severity, Transfer
Importance, Manager Influence, Player Importance, Competition Importance, Timing, Historical
Impact, Community Momentum. Generate: Impact Score, Confidence, Affected Teams, Affected
Players, Affected Competitions.").

Every factor is a real, deterministic heuristic computed from data this milestone already
persists (`NewsEvent`, prior `ImpactScore`s, `SentimentResult` momentum) — no ML model, the same
"framework, not overengineered" posture the Similarity Engine took in Milestone 7. Categorizing
affected entities into Teams/Players/Competitions optionally consults the Knowledge Graph's
`KGNodeRepositoryPort` (Milestone 5/7) when an affected ref is a resolved node id — "using
existing Graph APIs only," not a new categorization mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from modules.intelligence.domain.entities import ImpactScore, NewsEvent
from modules.intelligence.domain.value_objects import ImpactScoreId, NewsEventType
from modules.intelligence.ports.repositories import ImpactScoreRepositoryPort, SentimentResultRepositoryPort
from modules.knowledge_graph.domain.value_objects import KGNodeId, NodeType
from modules.knowledge_graph.ports.repositories import KGNodeRepositoryPort

_SEVERE_INJURY_TERMS = ("acl", "fracture", "surgery", "long-term", "ruptured", "torn")
_MINOR_INJURY_TERMS = ("knock", "doubt", "minor", "precaution")

# Baseline competition-importance weight per event type — how much this kind of news typically
# affects a competition's standing/trajectory, independent of any specific competition.
_COMPETITION_IMPORTANCE_BY_EVENT_TYPE = {
    NewsEventType.TRANSFER: 0.6,
    NewsEventType.INJURY: 0.5,
    NewsEventType.RECOVERY: 0.3,
    NewsEventType.SUSPENSION: 0.5,
    NewsEventType.MANAGER_CHANGE: 0.7,
    NewsEventType.FORMATION_CHANGE: 0.3,
    NewsEventType.TACTICAL_CHANGE: 0.3,
    NewsEventType.TRAINING_UPDATE: 0.2,
    NewsEventType.WEATHER_REPORT: 0.3,
    NewsEventType.TRAVEL_DELAY: 0.3,
    NewsEventType.STADIUM_CHANGE: 0.4,
    NewsEventType.MATCH_POSTPONEMENT: 0.8,
    NewsEventType.PLAYER_AVAILABILITY: 0.4,
    NewsEventType.LINEUP_EXPECTATION: 0.3,
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _looks_like_node_id(ref: str) -> KGNodeId | None:
    try:
        return KGNodeId(UUID(ref))
    except ValueError:
        return None


@dataclass
class NewsImpactEngine:
    impact_scores: ImpactScoreRepositoryPort
    sentiment_results: SentimentResultRepositoryPort
    kg_nodes: KGNodeRepositoryPort | None = None
    historical_baseline_window: int = 20

    async def score(self, event: NewsEvent, now: datetime) -> ImpactScore:
        factors = {
            "injury_severity": self._injury_severity(event),
            "transfer_importance": self._transfer_importance(event),
            "manager_influence": 0.8 if event.event_type is NewsEventType.MANAGER_CHANGE else 0.0,
            "player_importance": self._player_importance(event),
            "competition_importance": _COMPETITION_IMPORTANCE_BY_EVENT_TYPE.get(event.event_type, 0.3),
            "timing": self._timing(event, now),
            "historical_impact": await self._historical_impact(),
            "community_momentum": await self._community_momentum(event),
        }
        impact_score = sum(factors.values()) / len(factors)

        affected_teams, affected_players, affected_competitions = await self._categorize_affected(event)

        record = ImpactScore(
            id=ImpactScoreId(uuid4()),
            news_event_id=event.id,
            impact_score=_clamp(impact_score),
            confidence=event.confidence,
            factors=factors,
            affected_teams=affected_teams,
            affected_players=affected_players,
            affected_competitions=affected_competitions,
            computed_at=now,
        )
        return await self.impact_scores.record(record)

    def _injury_severity(self, event: NewsEvent) -> float:
        if event.event_type is not NewsEventType.INJURY:
            return 0.0
        lowered = event.summary.lower()
        if any(term in lowered for term in _SEVERE_INJURY_TERMS):
            return 0.9
        if any(term in lowered for term in _MINOR_INJURY_TERMS):
            return 0.3
        return 0.5

    def _transfer_importance(self, event: NewsEvent) -> float:
        if event.event_type is not NewsEventType.TRANSFER:
            return 0.0
        return _clamp(0.5 + 0.1 * min(len(event.affected_entity_refs), 5))

    def _player_importance(self, event: NewsEvent) -> float:
        if not event.affected_entity_refs:
            return 0.0
        resolved = sum(1 for ref in event.affected_entity_refs if _looks_like_node_id(ref) is not None)
        return resolved / len(event.affected_entity_refs)

    def _timing(self, event: NewsEvent, now: datetime) -> float:
        occurred_at = event.occurred_at
        if occurred_at.tzinfo is None and now.tzinfo is not None:
            occurred_at = occurred_at.replace(tzinfo=now.tzinfo)
        age_hours = max(0.0, (now - occurred_at).total_seconds() / 3600)
        if age_hours <= 24:
            return 1.0
        # linear decay from 1.0 at 24h to 0.1 at 7 days (168h), floored at 0.1
        decayed = 1.0 - (age_hours - 24) / (168 - 24) * 0.9
        return _clamp(decayed, low=0.1)

    async def _historical_impact(self) -> float:
        recent = await self.impact_scores.list_recent(limit=self.historical_baseline_window)
        if not recent:
            return 0.5
        return sum(r.impact_score for r in recent) / len(recent)

    async def _community_momentum(self, event: NewsEvent) -> float:
        if not event.affected_entity_refs:
            return 0.0
        magnitudes = []
        for ref in event.affected_entity_refs:
            readings = await self.sentiment_results.list_for_entity(ref, limit=1)
            if readings:
                magnitudes.append(abs(readings[0].momentum) / 2.0)  # momentum spans [-2, 2]
        if not magnitudes:
            return 0.0
        return _clamp(sum(magnitudes) / len(magnitudes))

    async def _categorize_affected(self, event: NewsEvent) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        if self.kg_nodes is None:
            return (), (), ()
        teams, players, competitions = [], [], []
        for ref in event.affected_entity_refs:
            node_id = _looks_like_node_id(ref)
            if node_id is None:
                continue
            node = await self.kg_nodes.get(node_id)
            if node is None:
                continue
            if node.node_type is NodeType.TEAM:
                teams.append(ref)
            elif node.node_type is NodeType.PLAYER:
                players.append(ref)
            elif node.node_type is NodeType.COMPETITION:
                competitions.append(ref)
        return tuple(teams), tuple(players), tuple(competitions)
