from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import redis.exceptions

from modules.features.application.feature_store_service import (
    FeatureNotActiveError,
    FeatureNotFoundError,
    FeatureStoreService,
)
from modules.features.domain.entities import FeatureDefinition
from modules.features.domain.value_objects import (
    EntityType,
    FeatureCategory,
    FeatureDataType,
    FeatureDefinitionId,
    FeatureKey,
    FeatureStatus,
    QualityFlag,
)

T0 = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _definition(status=FeatureStatus.ACTIVE, expected_range=None, data_type=FeatureDataType.FLOAT) -> FeatureDefinition:
    return FeatureDefinition(
        id=FeatureDefinitionId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        name="Possession %",
        description="d",
        sport_code="football",
        category=FeatureCategory.TEAM,
        formula="possession_seconds / match_seconds",
        data_type=data_type,
        owner="data-team",
        entity_type=EntityType.TEAM,
        status=status,
        expected_range=expected_range,
    )


@pytest.fixture
def service(definition_repo, value_repo, online_store):
    return FeatureStoreService(definitions=definition_repo, offline=value_repo, online=online_store)


@pytest.mark.asyncio
async def test_write_requires_registered_feature(service):
    with pytest.raises(FeatureNotFoundError):
        await service.write("does.not.exist", EntityType.TEAM, "team-1", 0.5, T0)


@pytest.mark.asyncio
async def test_write_requires_active_status_by_default(service, definition_repo):
    await definition_repo.upsert(_definition(status=FeatureStatus.DRAFT))

    with pytest.raises(FeatureNotActiveError):
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.5, T0)


@pytest.mark.asyncio
async def test_write_allows_draft_when_require_active_is_false(service, definition_repo):
    await definition_repo.upsert(_definition(status=FeatureStatus.DRAFT))

    value = await service.write(
        "football.team.possession_pct", EntityType.TEAM, "team-1", 0.5, T0, require_active=False
    )

    assert value.value == 0.5


@pytest.mark.asyncio
async def test_write_flags_type_mismatch(service, definition_repo):
    await definition_repo.upsert(_definition())

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", "not-a-number", T0)

    assert value.quality_flags == (QualityFlag.TYPE_MISMATCH,)


@pytest.mark.asyncio
async def test_write_flags_out_of_range(service, definition_repo):
    await definition_repo.upsert(_definition(expected_range=(0.0, 1.0)))

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 1.5, T0)

    assert value.quality_flags == (QualityFlag.OUT_OF_RANGE,)


@pytest.mark.asyncio
async def test_write_ok_within_range(service, definition_repo):
    await definition_repo.upsert(_definition(expected_range=(0.0, 1.0)))

    value = await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.55, T0)

    assert value.quality_flags == (QualityFlag.OK,)


@pytest.mark.asyncio
async def test_write_persists_to_both_offline_and_online(service, definition_repo, value_repo, online_store):
    await definition_repo.upsert(_definition())

    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    assert len(value_repo.store) == 1
    cached = await online_store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")
    assert cached is not None and cached.value == 0.6


@pytest.mark.asyncio
async def test_read_prefers_online_cache(service, definition_repo, online_store):
    await definition_repo.upsert(_definition())
    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)
    # mutate the cached copy directly to prove read comes from online, not offline
    cached = await online_store.get(FeatureKey("football.team.possession_pct"), EntityType.TEAM, "team-1")
    from dataclasses import replace

    await online_store.set(replace(cached, value=0.99), ttl_seconds=60)

    read = await service.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read.value == 0.99


@pytest.mark.asyncio
async def test_read_falls_back_to_offline_on_cache_miss(service, definition_repo, value_repo):
    await definition_repo.upsert(_definition())
    await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)
    # simulate cache eviction — online store is untouched but we read via a fresh empty online store
    empty_online = type(service.online)()
    service_with_empty_cache = FeatureStoreService(definitions=service.definitions, offline=value_repo, online=empty_online)

    read = await service_with_empty_cache.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read is not None
    assert read.value == 0.6


@pytest.mark.asyncio
async def test_read_returns_none_when_nothing_written(service, definition_repo):
    await definition_repo.upsert(_definition())

    assert await service.read("football.team.possession_pct", EntityType.TEAM, "team-1") is None


@dataclass
class _UnreachableOnlineFeatureStore:
    """Stands in for a Redis-backed online store whose connection is down — every call raises
    the same `redis.exceptions.RedisError` subclass a real dead connection would."""

    store: dict = field(default_factory=dict)

    async def get(self, feature_key, entity_type, entity_id):
        raise redis.exceptions.ConnectionError("connection refused")

    async def set(self, value, ttl_seconds):
        raise redis.exceptions.ConnectionError("connection refused")

    async def delete(self, feature_key, entity_type, entity_id):
        raise redis.exceptions.ConnectionError("connection refused")


@pytest.mark.asyncio
async def test_write_persists_offline_even_when_online_cache_is_unreachable(service, definition_repo, value_repo):
    """Audit fix 2026-08-02: a Redis outage during write() used to raise straight out of the
    method and roll back the whole (already-durable) offline write along with it. The durable
    record must survive a cache outage — that's the module's own documented contract."""
    await definition_repo.upsert(_definition())
    unreachable = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=_UnreachableOnlineFeatureStore())

    value = await unreachable.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    assert value.value == 0.6
    assert len(value_repo.store) == 1


@pytest.mark.asyncio
async def test_read_falls_back_to_offline_when_online_cache_is_unreachable(service, definition_repo, value_repo):
    """A cache outage on read() must degrade exactly like a cache miss, not raise."""
    await definition_repo.upsert(_definition())
    healthy = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=service.online)
    await healthy.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.6, T0)

    unreachable = FeatureStoreService(definitions=definition_repo, offline=value_repo, online=_UnreachableOnlineFeatureStore())
    read = await unreachable.read("football.team.possession_pct", EntityType.TEAM, "team-1")

    assert read is not None
    assert read.value == 0.6


def test_is_stale():
    value = _write_value_stub()
    assert FeatureStoreService.is_stale(value, T0 + timedelta(hours=2), max_staleness_seconds=3600)
    assert not FeatureStoreService.is_stale(value, T0 + timedelta(minutes=30), max_staleness_seconds=3600)


def _write_value_stub():
    from modules.features.domain.entities import FeatureValue
    from modules.features.domain.value_objects import FeatureValueId

    return FeatureValue(
        id=FeatureValueId(uuid4()),
        feature_key=FeatureKey("football.team.possession_pct"),
        entity_type=EntityType.TEAM,
        entity_id="team-1",
        as_of=T0,
        value=0.5,
    )


class TestPointInTimeLeakagePrevention:
    """Milestone 4 item 11 — the 7 named leakage-prevention scenarios (A-G), exercised against
    `FeatureStoreService.read_as_of()`: the real production entry point for point-in-time reads
    (backtesting, training-dataset assembly, reconstructing what a past prediction should have
    seen). `read_as_of` deliberately bypasses `online` (see its own docstring — the cache has no
    as-of dimension), so these tests go through `service.read_as_of`, not a raw repository call,
    to prove the actual served path is leak-safe, not just the repository underneath it.

    All 7 scenarios reduce to one real mechanism — `FeatureValueModel.as_of <= cutoff` filtering
    — since `as_of` is the Feature Store schema's only temporal-validity dimension today (it's
    NOT NULL, so "unknown timestamp" cannot literally occur in this table; see test C's docstring
    for where that concept actually lives instead). Naming each scenario after the milestone
    spec's own vocabulary (kickoff/post-match/future-fixture/versioned/late-ingested) rather than
    collapsing them into one generic test, so a future regression in any one of these framings is
    caught and named accurately, even though today they share one code path."""

    KICKOFF = T0 + timedelta(hours=2)

    @pytest.mark.asyncio
    async def test_a_pre_kickoff_value_is_included(self, service, definition_repo):
        await definition_repo.upsert(_definition())
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.55, T0)

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", self.KICKOFF)

        assert read is not None
        assert read.value == pytest.approx(0.55)

    @pytest.mark.asyncio
    async def test_b_post_kickoff_value_is_excluded(self, service, definition_repo):
        await definition_repo.upsert(_definition())
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.61, self.KICKOFF + timedelta(minutes=45))

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", self.KICKOFF)

        assert read is None

    async def test_c_unknown_timestamp_has_no_representation_in_the_feature_store(self):
        """`FeatureValueModel.as_of` is `Mapped[datetime]` (NOT NULL) — a Feature Store value
        genuinely cannot exist without a timestamp, so "unknown-timestamp excluded by default"
        isn't a Feature Store behavior to test here. The real analogue lives in the *structured*
        intelligence domain (injuries/transfers/lineups), where `availability_classification`
        defaults to `UNKNOWN_AVAILABILITY_TIME` for exactly this reason — covered by
        tests/unit/modules/ingestion/test_entity_reconciliation_service.py's injury/transfer
        reconciliation tests and confirmed for every existing dev.db row in the Milestone 4
        verification report. Documented here (not skipped silently) so this scenario's absence
        from the Feature Store suite is a deliberate, explained finding, not an oversight."""

    @pytest.mark.asyncio
    async def test_d_post_match_stat_value_is_excluded_at_a_pre_match_cutoff(self, service, definition_repo):
        """Same mechanism as scenario B, named for the milestone spec's own "post-match stats"
        framing: a full-time statistic (e.g. final possession %) written with `as_of=full_time`
        must not leak into a prediction context built at kickoff."""
        await definition_repo.upsert(_definition())
        full_time = self.KICKOFF + timedelta(minutes=95)
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.58, full_time)

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", self.KICKOFF)

        assert read is None

    @pytest.mark.asyncio
    async def test_e_future_fixture_has_no_stats_available_at_an_earlier_cutoff(self, service, definition_repo):
        """A fixture that hasn't happened yet has no feature values with `as_of` at or before the
        query cutoff at all — `read_as_of` must return None outright, not a stale/wrong value."""
        await definition_repo.upsert(_definition())
        far_future_match = self.KICKOFF + timedelta(days=30)
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.5, far_future_match)

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", self.KICKOFF)

        assert read is None

    @pytest.mark.asyncio
    async def test_f_versioned_historical_retrieval_returns_the_value_true_at_that_cutoff(self, service, definition_repo):
        """Multiple `as_of` versions exist for the same entity/feature (form index recomputed
        after each fixture) — `read_as_of` at a mid-history cutoff must return the version that
        was current *then*, not the latest version overall (which would leak future recomputation
        into a historical reconstruction) and not the oldest (which would understate what was
        actually known by that point)."""
        await definition_repo.upsert(_definition())
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.40, T0)
        mid_cutoff = T0 + timedelta(days=10)
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.45, mid_cutoff)
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.70, mid_cutoff + timedelta(days=20))

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", mid_cutoff + timedelta(days=1))

        assert read.value == pytest.approx(0.45)

    @pytest.mark.asyncio
    async def test_g_late_ingested_value_with_an_early_as_of_is_still_included(self, service, definition_repo, value_repo):
        """Ingestion order must never substitute for temporal validity: a value whose *real-world*
        `as_of` predates the cutoff is included even if it was the last one written to the store
        (e.g. a delayed sync catching up on older data) — proving `read_as_of` filters strictly by
        `as_of`, never by insertion order or `list`/row position."""
        await definition_repo.upsert(_definition())
        # Write the *later* real-world value first, then backfill an *earlier* one — insertion
        # order is the reverse of chronological order, and the query result must not care.
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.65, T0 + timedelta(days=5))
        await service.write("football.team.possession_pct", EntityType.TEAM, "team-1", 0.50, T0)
        assert value_repo.store[-1].as_of == T0  # sanity: the early value really was written last

        read = await service.read_as_of("football.team.possession_pct", EntityType.TEAM, "team-1", T0 + timedelta(hours=1))

        assert read.value == pytest.approx(0.50)
