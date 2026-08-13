"""Milestone 10 §4 — deterministic relevance pre-filter, the real cost-control gap the
pre-implementation audit identified: every article ingested through the real pipeline was
previously sent to Gemini unconditionally (twice — `extract_events` + `extract_entities`), with
no pre-filtering at all.

Explicitly NOT a resolution step and NOT a replacement for real extraction — entity resolution
still happens exactly as Milestone 9 built it, entirely after Gemini runs
(`EntityExtractionService.extract_and_link` against the Knowledge Graph). This filter only decides
whether an article is worth spending a Gemini call on at all; it is deterministic keyword matching,
not semantic understanding, and will occasionally false-positive (a team name appearing in an
unrelated context) — that is an accepted, documented limitation of a cost pre-filter, not a defect
in the resolution pipeline it sits in front of.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from modules.knowledge_graph.domain.value_objects import NodeType
from modules.sports.domain.value_objects import FixtureStatus, SeasonId


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


@dataclass(frozen=True)
class NewsRelevanceFilter:
    """``vocabulary`` is a set of already-normalized terms (canonical team/player names plus their
    Knowledge Graph aliases) — built fresh per scheduled run from the fixtures actually upcoming
    within the configured window, never hardcoded. Word-boundary matching (not raw substring)
    avoids the most obvious false-positive class — e.g. a short team nickname matching inside an
    unrelated longer word — while still being simple, deterministic, and cheap."""

    vocabulary: frozenset[str]

    def is_relevant(self, title: str, body: str) -> bool:
        if not self.vocabulary:
            return False
        haystack = normalize_text(f"{title} {body}")
        for term in self.vocabulary:
            if not term:
                continue
            if re.search(r"\b" + re.escape(term) + r"\b", haystack):
                return True
        return False


def build_vocabulary(names: list[str]) -> frozenset[str]:
    return frozenset(normalize_text(name) for name in names if name and name.strip())


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007) — same duplicated
    helper used throughout this codebase's ingestion/intelligence modules."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


async def build_fixture_relevance_vocabulary(
    *, fixtures, teams, players, kg_nodes, season_id: SeasonId, now: datetime, window_hours: float,
) -> frozenset[str]:
    """Milestone 10's real Knowledge Graph reuse, extracted here (Milestone 12) so both
    `ScheduledNewsSyncService` (upcoming-fixture window) and `NewsBackfillService` (same shape,
    different window) share one vocabulary-building mechanism instead of a second one being
    invented for backfill — for every team/player involved in a fixture scheduled within
    ``[now, now + window_hours]``, collects its canonical name plus every Knowledge Graph alias
    already on record, exactly the same ``kg_nodes.get_by_entity_ref`` round trip
    `NewsMarketImpactEngine` and the original M10 implementation already perform. Repository
    ports are duck-typed (``list_by_season``/``get``/``list_by_team``/``get_by_entity_ref``) —
    deliberately untyped here so both real repositories and test fakes satisfy it identically."""
    all_fixtures = await fixtures.list_by_season(season_id)
    window_end = now + timedelta(hours=window_hours)
    upcoming = [
        f for f in all_fixtures
        if f.status is FixtureStatus.SCHEDULED and now <= _ensure_aware(f.scheduled_at, now) <= window_end
    ]

    names: list[str] = []
    seen_team_ids: set[str] = set()
    for fixture in upcoming:
        for team_id in (fixture.home_team_id, fixture.away_team_id):
            key = str(team_id.value)
            if key in seen_team_ids:
                continue
            seen_team_ids.add(key)
            team = await teams.get(team_id)
            if team is None:
                continue
            names.append(team.name)
            team_node = await kg_nodes.get_by_entity_ref(NodeType.TEAM, key)
            if team_node is not None:
                names.extend(team_node.aliases)

            for player in await players.list_by_team(team_id):
                names.append(player.name)
                player_node = await kg_nodes.get_by_entity_ref(NodeType.PLAYER, str(player.id.value))
                if player_node is not None:
                    names.extend(player_node.aliases)

    return build_vocabulary(names)
