"""Gemini Prediction Reasoning Engine — live, cutoff-safe evidence collection (spec Phases 5-6).

Reuses Milestone 5's real point-in-time-safety mechanism unchanged: every `NewsEvent`/`Injury`/
`Transfer`/`Lineup` this codebase persists already carries `information_available_at`/
`availability_classification` ("VERIFIED_PRE_MATCH" | "VERIFIED_POST_MATCH" |
"UNKNOWN_AVAILABILITY_TIME", never auto-classified). This module does not invent a second
timestamp-safety scheme — it filters on that existing field, and `NewsEvent.is_feature_eligible()`
(the exact choke point every other feature-writing consumer already uses) for news specifically.
An item with no verified pre-match timestamp is rejected, not silently treated as "no news
exists" (absolute rule: missing information is never inferred as negative/absent information).

No new provider, no new repository — every fetch below goes through the same
`NewsEventRepositoryPort`/`InjuryRepositoryPort`/`TransferRepositoryPort`/`LineupRepositoryPort`
`ExplainabilityEngine`/`EntityReconciliationService` already depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from modules.intelligence.ports.repositories import NewsEventRepositoryPort
from modules.predictions.domain.context_categories import context_categories_for
from modules.predictions.domain.contextual_reasoning import EvidenceItem
from modules.sports.domain.value_objects import FixtureId
from modules.sports.ports.repositories import (
    FixtureRepositoryPort,
    InjuryRepositoryPort,
    LineupRepositoryPort,
    TransferRepositoryPort,
)

_LINEUP_WINDOW = 5


@dataclass(frozen=True)
class GatheredEvidence:
    items_by_category: dict[str, tuple[EvidenceItem, ...]] = field(default_factory=dict)
    missing_context: tuple[str, ...] = field(default_factory=tuple)
    accepted_count: int = 0
    rejected_count: int = 0
    rejection_reasons: dict[str, int] = field(default_factory=dict)


@dataclass
class LiveEvidenceGatherer:
    fixtures: FixtureRepositoryPort
    news: NewsEventRepositoryPort
    injuries: InjuryRepositoryPort
    transfers: TransferRepositoryPort
    lineups: LineupRepositoryPort

    async def gather(self, subject_ref: str, sport_code: str, prediction_cutoff: datetime) -> GatheredEvidence:
        categories = context_categories_for(sport_code)
        items: dict[str, list[EvidenceItem]] = {c: [] for c in categories}
        missing: list[str] = []
        accepted = 0
        rejected = 0
        reasons: dict[str, int] = {}

        def _reject(reason: str) -> None:
            nonlocal rejected
            rejected += 1
            reasons[reason] = reasons.get(reason, 0) + 1

        if "news" in categories:
            for event in await self.news.list_for_entity(subject_ref, limit=50):
                if not event.is_feature_eligible():
                    _reject("news_not_verified_pre_match")
                    continue
                if event.information_available_at is None or event.information_available_at > prediction_cutoff:
                    _reject("news_after_cutoff")
                    continue
                accepted += 1
                items["news"].append(
                    EvidenceItem(
                        source_id=str(event.id.value), category="news", summary=event.summary,
                        entity_ref=subject_ref, source_name=str(event.source_id),
                        published_at=event.occurred_at, retrieved_at=event.detected_at,
                    )
                )
            if not items["news"]:
                missing.append("news")

        team_categories = tuple(c for c in categories if c != "news")
        fixture = None
        if team_categories:
            try:
                fixture = await self.fixtures.get(FixtureId(UUID(subject_ref)))
            except ValueError:
                fixture = None  # subject_ref isn't a fixture UUID (e.g. a team/player-scoped prediction)

        if team_categories and fixture is None:
            missing.extend(team_categories)
        elif fixture is not None:
            team_ids = (fixture.home_team_id, fixture.away_team_id)

            if "injuries" in categories:
                for team_id in team_ids:
                    for injury in await self.injuries.list_current_by_team(team_id):
                        if injury.information_available_at is None or injury.information_available_at > prediction_cutoff:
                            _reject("injury_after_cutoff_or_unverified")
                            continue
                        accepted += 1
                        summary = injury.status + (f" ({injury.reason})" if injury.reason else "")
                        items["injuries"].append(
                            EvidenceItem(
                                source_id=str(injury.id.value), category="injuries", summary=summary,
                                entity_ref=str(team_id.value), published_at=injury.reported_at,
                                retrieved_at=injury.fetched_at,
                            )
                        )
                if not items["injuries"]:
                    missing.append("injuries")

            if "transfers" in categories:
                for team_id in team_ids:
                    for transfer in await self.transfers.list_by_team(team_id):
                        if transfer.information_available_at is None or transfer.information_available_at > prediction_cutoff:
                            _reject("transfer_after_cutoff_or_unverified")
                            continue
                        accepted += 1
                        items["transfers"].append(
                            EvidenceItem(
                                source_id=str(transfer.id.value), category="transfers",
                                summary=transfer.transfer_type or "transfer",
                                entity_ref=str(team_id.value), published_at=transfer.effective_date,
                                retrieved_at=transfer.fetched_at,
                            )
                        )
                if not items["transfers"]:
                    missing.append("transfers")

            if "lineups" in categories:
                for team_id in team_ids:
                    for lineup in await self.lineups.list_recent_by_team(team_id, prediction_cutoff, limit=_LINEUP_WINDOW):
                        if lineup.information_available_at is None or lineup.information_available_at > prediction_cutoff:
                            _reject("lineup_after_cutoff_or_unverified")
                            continue
                        accepted += 1
                        formation = lineup.formation or "formation unconfirmed"
                        items["lineups"].append(
                            EvidenceItem(
                                source_id=str(lineup.id.value), category="lineups",
                                summary=f"{formation}, {len(lineup.slots)} slots",
                                entity_ref=str(team_id.value), published_at=lineup.information_available_at,
                                retrieved_at=lineup.fetched_at,
                            )
                        )
                if not items["lineups"]:
                    missing.append("lineups")

        return GatheredEvidence(
            items_by_category={k: tuple(v) for k, v in items.items()},
            missing_context=tuple(missing),
            accepted_count=accepted,
            rejected_count=rejected,
            rejection_reasons=reasons,
        )
