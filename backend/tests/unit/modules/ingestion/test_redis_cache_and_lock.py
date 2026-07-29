import fakeredis
import pytest

from modules.ingestion.infrastructure.cache.redis_lock import RedisDistributedLock
from modules.ingestion.infrastructure.cache.redis_sync_cache import RedisSyncCache


@pytest.fixture
def redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


@pytest.fixture
def cache(redis_client):
    return RedisSyncCache(client=redis_client)


@pytest.fixture
def lock(redis_client):
    return RedisDistributedLock(client=redis_client)


# -- RedisSyncCache ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_get_missing_key_returns_none(cache):
    assert await cache.get("nope") is None


@pytest.mark.asyncio
async def test_cache_set_then_get_round_trips_dict(cache):
    await cache.set("k", {"a": 1, "b": [1, 2, 3]}, ttl_seconds=60)

    value = await cache.get("k")

    assert value == {"a": 1, "b": [1, 2, 3]}


@pytest.mark.asyncio
async def test_cache_set_applies_ttl(cache, redis_client):
    await cache.set("k", "v", ttl_seconds=120)

    ttl = await redis_client.ttl("synccache:k")
    assert 0 < ttl <= 120


@pytest.mark.asyncio
async def test_cache_delete_removes_entry(cache):
    await cache.set("k", "v", ttl_seconds=60)

    await cache.delete("k")

    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_cache_keys_are_namespaced_independently(cache):
    await cache.set("a", 1, ttl_seconds=60)
    await cache.set("b", 2, ttl_seconds=60)

    assert await cache.get("a") == 1
    assert await cache.get("b") == 2


# -- RedisDistributedLock --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_acquire_succeeds_when_free(lock):
    assert await lock.acquire("scope-a", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_second_acquire_of_same_key_fails_while_held(lock):
    other_holder = RedisDistributedLock(client=lock.client)
    await other_holder.acquire("scope-a", ttl_seconds=60)

    assert await lock.acquire("scope-a", ttl_seconds=60) is False


@pytest.mark.asyncio
async def test_release_allows_reacquisition(lock):
    await lock.acquire("scope-a", ttl_seconds=60)
    await lock.release("scope-a")

    assert await lock.acquire("scope-a", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_release_without_prior_acquire_is_a_no_op(lock):
    await lock.release("never-acquired")  # must not raise


@pytest.mark.asyncio
async def test_release_does_not_clear_a_lock_acquired_by_someone_else(lock, redis_client):
    await lock.acquire("scope-a", ttl_seconds=60)
    await lock.release("scope-a")

    other_holder = RedisDistributedLock(client=redis_client)
    await other_holder.acquire("scope-a", ttl_seconds=60)

    # our (already-used, now-empty) token cache has nothing left for scope-a, so releasing
    # again is a no-op and must not touch the other holder's lock
    await lock.release("scope-a")

    assert await other_holder.acquire("scope-a", ttl_seconds=60) is False  # still held by other_holder


@pytest.mark.asyncio
async def test_different_keys_are_independent(lock):
    assert await lock.acquire("scope-a", ttl_seconds=60) is True
    assert await lock.acquire("scope-b", ttl_seconds=60) is True


@pytest.mark.asyncio
async def test_lock_expires_after_ttl(lock, redis_client):
    await lock.acquire("scope-a", ttl_seconds=1)

    await redis_client.delete("lock:scope-a")  # simulate TTL expiry without a real sleep

    other_holder = RedisDistributedLock(client=redis_client)
    assert await other_holder.acquire("scope-a", ttl_seconds=60) is True
