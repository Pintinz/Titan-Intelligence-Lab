from __future__ import annotations

from datetime import datetime, timedelta, timezone

from modules.intelligence.application.community_ingestion_service import (
    CommunityIngestionService,
    is_bot_author,
    is_noise,
    is_spam,
    post_content_hash,
)
from modules.intelligence.domain.value_objects import CommunityPlatform, SyncStatus, SyncTrigger
from modules.intelligence.infrastructure.persistence.repositories import (
    SqlAlchemyCommunityPostRepository,
    SqlAlchemyIntelligenceSyncCheckpointRepository,
    SqlAlchemyIntelligenceSyncRunRepository,
)
from modules.intelligence.infrastructure.providers.mock_community_provider import MockCommunityProvider
from modules.intelligence.ports.community_provider import RawCommunityPostRecord

T0 = datetime(2026, 7, 26, tzinfo=timezone.utc)


def _service(sqlite_session, provider=None):
    posts = SqlAlchemyCommunityPostRepository(session=sqlite_session)
    checkpoints = SqlAlchemyIntelligenceSyncCheckpointRepository(session=sqlite_session)
    sync_runs = SqlAlchemyIntelligenceSyncRunRepository(session=sqlite_session)
    providers = {CommunityPlatform.REDDIT.value: provider} if provider else {}
    return CommunityIngestionService(posts=posts, checkpoints=checkpoints, sync_runs=sync_runs, providers=providers)


def test_is_spam_detects_known_markers():
    assert is_spam("Click here to win big prizes!") is True


def test_is_spam_detects_excessive_shouting():
    assert is_spam("THIS IS AMAZING NEWS TODAY EVERYONE") is True


def test_is_spam_false_for_normal_text():
    assert is_spam("I think the manager should change formation next game.") is False


def test_is_bot_author_detects_trailing_digits():
    assert is_bot_author("footballfan1234567") is True


def test_is_bot_author_false_for_normal_handle():
    assert is_bot_author("real_supporter_99") is False


def test_is_noise_detects_too_short_text():
    assert is_noise("ok") is True


def test_is_noise_detects_punctuation_only():
    assert is_noise("!!!...") is True


def test_is_noise_false_for_real_content():
    assert is_noise("Great performance from the midfield today.") is False


def test_post_content_hash_stable_and_platform_scoped():
    a = post_content_hash(CommunityPlatform.REDDIT, "Great win today!")
    b = post_content_hash(CommunityPlatform.TWITTER, "Great win today!")
    c = post_content_hash(CommunityPlatform.REDDIT, "great   win today!")

    assert a != b  # different platform, same text -> different hash
    assert a == c  # same platform, whitespace/case-insensitive normalized text -> same hash


async def test_sync_topic_creates_posts(sqlite_session):
    provider = MockCommunityProvider(
        platform=CommunityPlatform.REDDIT,
        fixed_posts=(
            RawCommunityPostRecord(
                external_id="p1", author_ref="real_fan_22", text="What a performance from the whole squad today.",
                posted_at=T0, engagement_score=0.5,
            ),
        ),
    )
    service = _service(sqlite_session, provider)

    run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.status == SyncStatus.SUCCEEDED
    assert run.items_created == 1


async def test_sync_topic_rejects_spam_and_bot_posts(sqlite_session):
    provider = MockCommunityProvider(
        platform=CommunityPlatform.REDDIT,
        fixed_posts=(
            RawCommunityPostRecord(
                external_id="p1", author_ref="real_fan_22", text="Click here to win free followers now!!!!",
                posted_at=T0,
            ),
            RawCommunityPostRecord(
                external_id="p2", author_ref="bot_account_9876543", text="Great match today, well played.",
                posted_at=T0,
            ),
            RawCommunityPostRecord(external_id="p3", author_ref="real_fan_23", text="ok", posted_at=T0),
        ),
    )
    service = _service(sqlite_session, provider)

    run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.items_rejected == 3
    assert run.items_created == 0


async def test_sync_topic_deduplicates_identical_text_within_batch(sqlite_session):
    provider = MockCommunityProvider(
        platform=CommunityPlatform.REDDIT,
        fixed_posts=(
            RawCommunityPostRecord(
                external_id="p1", author_ref="fan_one", text="Excellent performance from the team tonight.",
                posted_at=T0,
            ),
            RawCommunityPostRecord(
                external_id="p2", author_ref="fan_two", text="Excellent performance from the team tonight.",
                posted_at=T0,
            ),
        ),
    )
    service = _service(sqlite_session, provider)

    run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    assert run.items_created == 1
    assert run.items_duplicate == 1


async def test_ingest_record_deduplicates_across_runs_by_external_id(sqlite_session):
    """`_ingest_record`'s ``seen_hashes`` set only covers one run; a post already persisted in
    an earlier run must still be caught via `CommunityPostRepositoryPort.get_by_external_id`."""
    service = _service(sqlite_session)
    record = RawCommunityPostRecord(
        external_id="p1", author_ref="fan_one", text="Loved the second half performance.", posted_at=T0,
    )

    first_outcome = await service._ingest_record(CommunityPlatform.REDDIT, record, T0, set())
    await sqlite_session.commit()
    second_outcome = await service._ingest_record(CommunityPlatform.REDDIT, record, T0, set())
    await sqlite_session.commit()

    assert first_outcome == "created"
    assert second_outcome == "duplicate"


async def test_sync_topic_credibility_bounded_by_engagement(sqlite_session):
    provider = MockCommunityProvider(
        platform=CommunityPlatform.REDDIT,
        fixed_posts=(
            RawCommunityPostRecord(
                external_id="p1", author_ref="fan_one", text="Solid defensive display from the back four.",
                posted_at=T0, engagement_score=1.0,
            ),
        ),
    )
    service = _service(sqlite_session, provider)

    await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(minutes=1))
    await sqlite_session.commit()

    stored = await service.posts.get_by_external_id(CommunityPlatform.REDDIT, "p1")
    assert stored.credibility_score == 1.0


async def test_sync_topic_missing_provider_raises(sqlite_session):
    service = _service(sqlite_session)

    try:
        await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0)
        assert False, "expected ValueError"
    except ValueError:
        pass


async def test_sync_topic_second_sync_passes_aware_checkpoint_to_provider(sqlite_session):
    """Regression coverage for the ADR-007 tz-fix path: a second sync must hand the provider an
    aware ``since`` even though SQLite dropped tzinfo from the persisted checkpoint."""
    early_post = RawCommunityPostRecord(
        external_id="p1", author_ref="fan_one", text="Early commentary about the match.", posted_at=T0,
    )
    late_post = RawCommunityPostRecord(
        external_id="p2", author_ref="fan_two", text="Later commentary about the match.",
        posted_at=T0 + timedelta(days=1),
    )
    provider = MockCommunityProvider(platform=CommunityPlatform.REDDIT, fixed_posts=(early_post, late_post))
    service = _service(sqlite_session, provider)

    first_run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(hours=1))
    await sqlite_session.commit()
    second_run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0 + timedelta(days=2))
    await sqlite_session.commit()

    assert first_run.items_fetched == 2  # since=None on first sync: everything
    assert second_run.items_fetched == 1  # since=checkpoint: only the later post


async def test_sync_topic_provider_failure_marks_run_failed(sqlite_session):
    class _FailingProvider:
        provider_key = "failing"
        platform = CommunityPlatform.REDDIT

        async def fetch_posts(self, topic, since=None, cursor=None):
            raise RuntimeError("rate limited")

    service = _service(sqlite_session, _FailingProvider())

    run = await service.sync_topic(CommunityPlatform.REDDIT, "my_team", T0, trigger=SyncTrigger.MANUAL)
    await sqlite_session.commit()

    assert run.status == SyncStatus.FAILED
    assert "rate limited" in run.error_message
