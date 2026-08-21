"""Gemini Prediction Reasoning Engine — `LiveEvidenceGatherer` cutoff/provenance filtering (spec
Phases 5-6, Part 2i). Reuses Milestone 5's real `information_available_at`/
`availability_classification` mechanism unchanged — these tests exercise that the gatherer
actually enforces it (future-timestamped and unverified items rejected, missing categories
reported honestly, never silently dropped) rather than re-testing Milestone 5 itself."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from modules.intelligence.domain.entities import NewsEvent, ResolvedNewsEntity
from modules.intelligence.domain.value_objects import (
    EntityResolutionStatus,
    NewsArticleId,
    NewsEventId,
    NewsEventType,
    NewsSourceId,
)
from modules.predictions.application.live_evidence_gatherer import LiveEvidenceGatherer
from modules.sports.domain.entities import Fixture, Injury, Lineup, Transfer
from modules.sports.domain.value_objects import EntityId, FixtureId, PlayerId, SeasonId, TeamId

T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)
HOME_TEAM = TeamId(uuid4())
AWAY_TEAM = TeamId(uuid4())
FIXTURE_ID = FixtureId(uuid4())


def _news_event(
    *, occurred_at: datetime, information_available_at: datetime | None, classification: str = "VERIFIED_PRE_MATCH"
) -> NewsEvent:
    return NewsEvent(
        id=NewsEventId(uuid4()), event_type=NewsEventType.INJURY, summary="Player doubtful for the match.",
        confidence=0.8, source_id=NewsSourceId(uuid4()), article_id=NewsArticleId(uuid4()),
        occurred_at=occurred_at, detected_at=occurred_at,
        resolved_entities=(
            ResolvedNewsEntity(ref="team-1", node_type="team", status=EntityResolutionStatus.RESOLVED),
        ),
        information_available_at=information_available_at, availability_classification=classification,
    )


@dataclass
class _FakeFixtureRepo:
    fixture: Fixture | None

    async def get(self, fixture_id):
        return self.fixture


@dataclass
class _FakeNewsRepo:
    events: list = field(default_factory=list)

    async def list_for_entity(self, entity_ref, limit=50):
        return self.events


@dataclass
class _FakeInjuryRepo:
    injuries: list = field(default_factory=list)

    async def list_current_by_team(self, team_id):
        return [i for i in self.injuries if getattr(i, "_team_id", None) == team_id]


@dataclass
class _FakeTransferRepo:
    transfers: list = field(default_factory=list)

    async def list_by_team(self, team_id):
        return [t for t in self.transfers if getattr(t, "_team_id", None) == team_id]


@dataclass
class _FakeLineupRepo:
    lineups: list = field(default_factory=list)

    async def list_recent_by_team(self, team_id, before, limit=10):
        return [l for l in self.lineups if getattr(l, "_team_id", None) == team_id]


def _fixture() -> Fixture:
    return Fixture(
        id=FIXTURE_ID, season_id=SeasonId(uuid4()), home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM,
        venue_id=None, scheduled_at=T0 + timedelta(days=1),
    )


def _gatherer(*, fixture=None, news=(), injuries=(), transfers=(), lineups=()) -> LiveEvidenceGatherer:
    return LiveEvidenceGatherer(
        fixtures=_FakeFixtureRepo(fixture=fixture),
        news=_FakeNewsRepo(events=list(news)),
        injuries=_FakeInjuryRepo(injuries=list(injuries)),
        transfers=_FakeTransferRepo(transfers=list(transfers)),
        lineups=_FakeLineupRepo(lineups=list(lineups)),
    )


@pytest.mark.asyncio
async def test_accepts_a_verified_pre_cutoff_news_item():
    event = _news_event(occurred_at=T0 - timedelta(hours=2), information_available_at=T0 - timedelta(hours=2))
    gatherer = _gatherer(fixture=_fixture(), news=[event])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert len(evidence.items_by_category["news"]) == 1
    assert evidence.accepted_count == 1
    assert "news" not in evidence.missing_context


@pytest.mark.asyncio
async def test_rejects_news_item_available_after_cutoff():
    event = _news_event(occurred_at=T0 + timedelta(hours=1), information_available_at=T0 + timedelta(hours=1))
    gatherer = _gatherer(fixture=_fixture(), news=[event])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert evidence.items_by_category["news"] == ()
    assert evidence.rejected_count == 1
    assert evidence.rejection_reasons["news_after_cutoff"] == 1
    assert "news" in evidence.missing_context


@pytest.mark.asyncio
async def test_rejects_news_item_not_verified_pre_match():
    """`is_feature_eligible()` (Milestone 5's real choke point) must reject an UNKNOWN or
    VERIFIED_POST_MATCH item even if its own timestamp looks like it's before the cutoff — a
    plausible-looking timestamp is not the same as a verified one."""
    event = _news_event(
        occurred_at=T0 - timedelta(hours=2), information_available_at=T0 - timedelta(hours=2),
        classification="UNKNOWN_AVAILABILITY_TIME",
    )
    gatherer = _gatherer(fixture=_fixture(), news=[event])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert evidence.items_by_category["news"] == ()
    assert evidence.rejection_reasons["news_not_verified_pre_match"] == 1


@pytest.mark.asyncio
async def test_missing_information_available_at_is_never_treated_as_present():
    """Absolute rule: missing information must never be silently inferred as available/negative
    — a `VERIFIED_PRE_MATCH` item with no `information_available_at` set is still rejected."""
    event = _news_event(occurred_at=T0 - timedelta(hours=2), information_available_at=None)
    gatherer = _gatherer(fixture=_fixture(), news=[event])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert evidence.items_by_category["news"] == ()
    assert evidence.rejection_reasons["news_after_cutoff"] == 1


@pytest.mark.asyncio
async def test_empty_news_category_is_reported_as_missing_not_fabricated_as_none():
    gatherer = _gatherer(fixture=_fixture(), news=[])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert evidence.items_by_category["news"] == ()
    assert "news" in evidence.missing_context


@pytest.mark.asyncio
async def test_non_uuid_subject_ref_marks_team_categories_missing_not_an_error():
    """A team- or player-scoped `subject_ref` (not a fixture UUID) must degrade to 'missing', not
    raise — `ValueError` from the UUID parse is caught inside the gatherer."""
    gatherer = _gatherer(fixture=None, news=[])

    evidence = await gatherer.gather("team-not-a-uuid", "football", T0)

    assert "injuries" in evidence.missing_context
    assert "transfers" in evidence.missing_context
    assert "lineups" in evidence.missing_context


@pytest.mark.asyncio
async def test_basketball_sport_only_gathers_its_own_real_categories():
    """`context_categories_for` is deliberately conservative — basketball has no dedicated
    transfer/lineup repository, so those categories must never appear at all, not even as
    'missing'."""
    gatherer = _gatherer(fixture=_fixture(), news=[])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "basketball", T0)

    assert set(evidence.items_by_category.keys()) == {"news", "injuries"}
    assert "transfers" not in evidence.missing_context
    assert "lineups" not in evidence.missing_context


@pytest.mark.asyncio
async def test_unregistered_sport_gathers_no_categories_at_all():
    gatherer = _gatherer(fixture=_fixture(), news=[])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "cricket", T0)

    assert evidence.items_by_category == {}
    assert evidence.missing_context == ()


@pytest.mark.asyncio
async def test_accepted_injury_within_cutoff_is_included():
    injury = Injury(
        id=EntityId(uuid4()), player_id=PlayerId(uuid4()), reported_at=T0 - timedelta(hours=3), status="OUT",
        reason="hamstring", availability_classification="VERIFIED_PRE_MATCH",
        information_available_at=T0 - timedelta(hours=3),
    )
    injury._team_id = HOME_TEAM
    gatherer = _gatherer(fixture=_fixture(), injuries=[injury])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert len(evidence.items_by_category["injuries"]) == 1
    assert "hamstring" in evidence.items_by_category["injuries"][0].summary


@pytest.mark.asyncio
async def test_injury_after_cutoff_is_rejected_and_category_reported_missing():
    injury = Injury(
        id=EntityId(uuid4()), player_id=PlayerId(uuid4()), reported_at=T0 + timedelta(hours=1), status="OUT",
        availability_classification="VERIFIED_PRE_MATCH", information_available_at=T0 + timedelta(hours=1),
    )
    injury._team_id = HOME_TEAM
    gatherer = _gatherer(fixture=_fixture(), injuries=[injury])

    evidence = await gatherer.gather(str(FIXTURE_ID.value), "football", T0)

    assert evidence.items_by_category["injuries"] == ()
    assert "injuries" in evidence.missing_context
    assert evidence.rejection_reasons["injury_after_cutoff_or_unverified"] == 1
