"""ProviderRouter — the single entry point ingestion code calls to fetch sports data. Ties
together everything the provider configuration directive asked for: automatic mock/real
selection, quota-aware throttling, circuit breaking, and response caching, so callers never
see any of that machinery (docs/admin_center.md §2).

POST-M24 Phase 2 ("Cache & Quota Safety"): the response cache moved from a process-local Python
`dict` to `SyncCachePort` (Redis-backed in production via `RedisSyncCache`, the same singleton
`SyncOrchestrator` already uses) so a cache write from one Celery worker is visible to every other
worker, not just the process that made it. Concurrent identical requests are deduplicated with the
existing `DistributedLockPort` (`RedisDistributedLock`) using double-checked locking: check cache,
try to acquire the lock, re-check cache after acquiring (the request that populated it may have
finished while this one waited), only the lock holder calls the provider. TTLs are now
endpoint-category-specific (`_ENDPOINT_TTL_SECONDS`) rather than one blanket per-provider number,
capped by whatever the admin configured on the provider itself. Real-adapter calls that fail with
a classified transient/rate-limited/network `ProviderRequestError`
(`api_sports_adapter.ProviderErrorKind`) get a small bounded backoff retry before the circuit
breaker/quota engine record the failure; a classified auth/permanent error never retries — see
`_call_with_retry`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.admin.application.circuit_breaker import CircuitBreaker, ProviderCircuitOpenError
from modules.admin.application.provider_management_service import ProviderManagementService
from modules.admin.application.quota_intelligence_engine import QuotaIntelligenceEngine
from modules.ingestion.ports.cache import SyncCachePort
from modules.ingestion.ports.lock import DistributedLockPort
from modules.sports.domain.value_objects import ProviderRef
from modules.sports.infrastructure.providers import provider_cache_codec
from modules.sports.infrastructure.providers.api_sports_adapter import ProviderErrorKind, ProviderRequestError
from modules.sports.ports.provider_gateway import (
    ProviderCoachRecord,
    ProviderCountryRecord,
    ProviderFixtureRecord,
    ProviderInjuryRecord,
    ProviderLineupRecord,
    ProviderOddsRecord,
    ProviderPlayerRecord,
    ProviderStandingRecord,
    ProviderTeamRecord,
    ProviderTeamStatisticsRecord,
    ProviderTransferRecord,
    SportsDataProviderPort,
)


class ProviderThrottledError(RuntimeError):
    """Raised when quota protection defers a low-priority request. Callers should serve cached/
    last-known-good data instead of failing the user-facing request outright ("graceful
    degradation", docs/admin_center.md §2)."""


class ProviderNotConfiguredError(RuntimeError):
    """Raised by `fetch_upcoming_fixtures` when the requested `provider_key` isn't registered in
    `fixture_schedule_adapters`, or is registered but not active/credentialed. Unlike
    `_resolve_adapter`'s per-sport default (which falls back to a mock so ordinary syncing never
    breaks), this call is only ever made for a competition that explicitly opted into a specific
    alternate provider (`CompetitionFixtureSourcePreference`) — silently falling back to mock
    data here would hide a real setup mistake instead of surfacing it."""


# Endpoint-category TTL policy (POST-M24 Phase 2 Step 5) — the same provider used to hand out one
# `cache_ttl_seconds` for every endpoint regardless of how often that endpoint's data actually
# changes. Keyed by the cache_key's first element (the "kind" every fetch_* method already
# passes). A kind not listed here falls back to the provider's own configured TTL, unchanged from
# pre-Phase-2 behavior. Initial policy targets per the restructuring brief — real endpoint
# semantics, not a guess: countries/coach are near-static reference data; completed fixtures are
# historical results that don't change once recorded; standings/injuries/odds/lineups need to stay
# fresh; transfers move on a daily cadence.
_ENDPOINT_TTL_SECONDS: dict[str, int] = {
    "countries": 7 * 24 * 3600,
    "teams": 24 * 3600,
    "players": 24 * 3600,
    "coach": 24 * 3600,
    "standings": 30 * 60,
    "standings_alt": 30 * 60,
    "team_statistics": 3 * 3600,
    "fixtures": 3600,
    "upcoming_fixtures": 3600,
    "completed_fixtures": 7 * 24 * 3600,
    "transfers": 12 * 3600,
    "injuries": 30 * 60,
    "lineups": 300,
    "odds": 600,
}

# Retry safety (Phase 2 Step 10): only these classified kinds are worth a bounded retry — auth and
# permanent errors will fail identically on a second attempt, so retrying just burns quota for the
# same outcome. Bounded to 2 extra attempts regardless of kind — this never retries indefinitely;
# Celery's own outer per-task retry (modules/ingestion/infrastructure/celery/tasks.py) remains a
# coarser, unrelated safety net on top of this, not a reason to retry more aggressively here.
_RETRYABLE_KINDS = frozenset({ProviderErrorKind.TRANSIENT, ProviderErrorKind.RATE_LIMITED, ProviderErrorKind.NETWORK})
_MAX_RETRY_ATTEMPTS = 2
_BASE_BACKOFF_SECONDS = 1.0

# Concurrent-request dedup (Phase 2 Step 7): how long a request that lost the lock race waits,
# polling the cache, before giving up and calling the provider itself — a safety valve so a lock
# holder that crashed/stalled never permanently blocks every other request for the same resource.
_LOCK_WAIT_ATTEMPTS = 10
_LOCK_WAIT_INTERVAL_SECONDS = 0.2
_LOCK_TTL_SECONDS = 30


@dataclass
class _InMemorySyncCache:
    """Default `SyncCachePort` when the caller doesn't inject a Redis-backed one (e.g. tests, or
    any embedder that doesn't need cross-process sharing) — same behavior `SportsProviderRouter`
    had built-in before Phase 2, just expressed against the port interface so production code and
    tests share one code path instead of the router special-casing "no cache configured". Real
    wall-clock TTL expiry (`datetime.now()`), matching how Redis's own `EX` actually behaves in
    production — the router's `now` parameter is a deterministic, caller-supplied clock used for
    circuit-breaker/quota bookkeeping, but `SyncCachePort` itself has no `now` parameter (Redis
    has no notion of a caller-supplied clock either), so this default mirrors that faithfully
    rather than inventing a deterministic-clock cache no real backend actually has."""

    _store: dict[str, tuple[datetime, object]] = field(default_factory=dict)

    async def get(self, key: str):
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if datetime.now() >= expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: object, ttl_seconds: int) -> None:
        self._store[key] = (datetime.now() + timedelta(seconds=ttl_seconds), value)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@dataclass
class _InMemoryDistributedLock:
    """Default `DistributedLockPort` when the caller doesn't inject a Redis-backed one. Correct
    mutual exclusion within one process (an `asyncio.Lock` per key, non-blocking `acquire`) —
    enough to exercise the double-checked-locking dedup path in tests without a real Redis
    instance; production always injects `RedisDistributedLock` for real cross-process locking."""

    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    _held: set[str] = field(default_factory=set)

    async def acquire(self, key: str, ttl_seconds: int) -> bool:
        if key in self._held:
            return False
        self._held.add(key)
        return True

    async def release(self, key: str) -> None:
        self._held.discard(key)


def _cache_key_for(kind_and_parts: tuple) -> str:
    """Stable, deterministic string key for a tuple cache key — every part is already a plain
    str/None (every `fetch_*` method below builds its tuple from provider/sport/ref strings), so
    a delimiter join is sufficient; `None` is rendered as a literal placeholder distinct from any
    real value so a missing `season_label` can never collide with a season actually named that."""
    return "providercache:" + "|".join("\x00" if part is None else str(part) for part in kind_and_parts)


def _cache_ttl_for(kind: str, provider_ttl: int) -> int:
    return _ENDPOINT_TTL_SECONDS.get(kind, provider_ttl)


@dataclass
class SportsProviderRouter:
    admin_service: ProviderManagementService
    quota_engine: QuotaIntelligenceEngine
    circuit_breaker: CircuitBreaker
    real_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
    mock_adapters: dict[str, SportsDataProviderPort]  # keyed by SportCode.value
    # Orthogonal to `real_adapters`: a second, provider-key-keyed slot for adapters that only
    # ever serve one narrow concern (today: upcoming fixture schedules) for a subset of
    # competitions, opted into explicitly per-competition rather than replacing a sport's
    # default adapter. Empty by default so existing callers/tests that don't pass this argument
    # are unaffected. See `fetch_upcoming_fixtures`.
    fixture_schedule_adapters: dict[str, SportsDataProviderPort] = field(default_factory=dict)
    # Both default to an in-memory implementation so existing/new tests work without a real Redis
    # instance; `apps/api/composition.py` injects the shared `get_redis_sync_cache()`/
    # `get_redis_lock()` singletons in production — the same ones `SyncOrchestrator` already uses.
    cache: SyncCachePort = field(default_factory=_InMemorySyncCache)
    lock: DistributedLockPort = field(default_factory=_InMemoryDistributedLock)

    async def _resolve_adapter(self, sport_code: str, now: datetime) -> tuple[SportsDataProviderPort, str]:
        real = self.real_adapters.get(sport_code)
        if real is None:
            return self.mock_adapters[sport_code], "mock"
        provider = await self.admin_service.providers.get_by_key(real.provider_key)
        if provider is None or not provider.is_usable():
            return self.mock_adapters[sport_code], "mock"
        credentials = await self.admin_service.usable_credentials(provider.id)
        if not credentials:
            return self.mock_adapters[sport_code], "mock"  # active provider, no key yet — dev mode
        return real, "real"

    async def _cache_get(self, cache_key: tuple):
        raw = await self.cache.get(_cache_key_for(cache_key))
        if raw is None:
            return None
        return provider_cache_codec.decode(raw)

    async def _cache_set(self, cache_key: tuple, value: object, ttl_seconds: int) -> None:
        await self.cache.set(_cache_key_for(cache_key), provider_cache_codec.encode(value), ttl_seconds)

    async def _call_with_retry(self, call, adapter):
        attempt = 0
        while True:
            try:
                return await call(adapter)
            except ProviderRequestError as exc:
                if exc.kind not in _RETRYABLE_KINDS or attempt >= _MAX_RETRY_ATTEMPTS:
                    raise
                delay = exc.retry_after_seconds or (_BASE_BACKOFF_SECONDS * (2**attempt))
                await asyncio.sleep(delay)
                attempt += 1

    async def _fetch_with_dedup(self, cache_key: tuple, fetch: callable):
        """Double-checked-locking dedup (Phase 2 Step 7): cache check -> try lock -> re-check
        cache after acquiring -> only the lock holder calls `fetch` -> cache the result -> release.
        A request that loses the lock race polls the cache for the winner's result, bounded, then
        falls through to calling the provider itself rather than blocking forever."""
        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        lock_key = _cache_key_for(cache_key)
        acquired = await self.lock.acquire(lock_key, _LOCK_TTL_SECONDS)
        if not acquired:
            for _ in range(_LOCK_WAIT_ATTEMPTS):
                await asyncio.sleep(_LOCK_WAIT_INTERVAL_SECONDS)
                cached = await self._cache_get(cache_key)
                if cached is not None:
                    return cached
            return await fetch()  # safety valve — never block indefinitely on a stalled holder

        try:
            cached = await self._cache_get(cache_key)  # mandatory re-check: may have populated while we waited to acquire
            if cached is not None:
                return cached
            return await fetch()
        finally:
            await self.lock.release(lock_key)

    async def _execute(
        self,
        sport_code: str,
        cache_key: tuple,
        now: datetime,
        low_priority: bool,
        call: callable,
    ):
        async def _fetch():
            adapter, mode = await self._resolve_adapter(sport_code, now)
            provider = await self.admin_service.providers.get_by_key(adapter.provider_key)
            cache_ttl = _cache_ttl_for(cache_key[0], provider.cache_ttl_seconds if provider else 3600)

            if mode == "real":
                if not self.circuit_breaker.allow_request(adapter.provider_key, now):
                    raise ProviderCircuitOpenError(f"circuit open for '{adapter.provider_key}'")
                if provider and await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority):
                    raise ProviderThrottledError(f"quota protection throttled '{adapter.provider_key}'")
                try:
                    result = await self._call_with_retry(call, adapter)
                except ProviderNotConfiguredError:
                    # Not evidence the provider itself is unhealthy — either a genuine missing
                    # capability, or (see _guard_same_provider) a caller-side cross-provider
                    # fixture-id mismatch. Recording either as a circuit/quota failure would let
                    # a structurally-impossible call (not a real api-sports.io fault) trip the
                    # breaker for every other, legitimate api-sports.io request.
                    raise
                except Exception:
                    self.circuit_breaker.record_failure(adapter.provider_key, now)
                    if provider:
                        await self.quota_engine.record_request(provider.id, now, success=False)
                    raise
                else:
                    self.circuit_breaker.record_success(adapter.provider_key)
                    if provider:
                        await self.quota_engine.record_request(provider.id, now, success=True)
            else:
                result = await call(adapter)  # mocks are free — no circuit/quota bookkeeping needed

            await self._cache_set(cache_key, result, cache_ttl)
            return result

        return await self._fetch_with_dedup(cache_key, _fetch)

    async def fetch_teams(
        self, sport_code: str, competition_ref: str, now: datetime, *,
        low_priority: bool = False, season_label: str | None = None,
    ) -> list[ProviderTeamRecord]:
        return await self._execute(
            sport_code,
            ("teams", sport_code, competition_ref, season_label),
            now,
            low_priority,
            lambda adapter: adapter.fetch_teams(competition_ref, season_label),
        )

    async def fetch_fixtures(
        self,
        sport_code: str,
        competition_ref: str,
        season_label: str,
        now: datetime,
        *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        return await self._execute(
            sport_code,
            ("fixtures", sport_code, competition_ref, season_label),
            now,
            low_priority,
            lambda adapter: adapter.fetch_fixtures(competition_ref, season_label, now),
        )

    async def fetch_countries(
        self, sport_code: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderCountryRecord]:
        return await self._execute(
            sport_code, ("countries", sport_code), now, low_priority,
            lambda adapter: adapter.fetch_countries(),
        )

    async def fetch_players(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *, low_priority: bool = False, season_label: str | None = None
    ) -> list[ProviderPlayerRecord]:
        return await self._execute(
            sport_code, ("players", sport_code, team_ref.provider, team_ref.external_id, season_label), now, low_priority,
            lambda adapter: adapter.fetch_players(team_ref, season_label),
        )

    async def fetch_standings(
        self, sport_code: str, competition_ref: str, season_label: str, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderStandingRecord]:
        return await self._execute(
            sport_code, ("standings", sport_code, competition_ref, season_label), now, low_priority,
            lambda adapter: adapter.fetch_standings(competition_ref, season_label),
        )

    def _guard_same_provider(self, fixture_ref: ProviderRef, call: callable) -> callable:
        """Real production incident (2026-08-30): `_execute` resolves its adapter purely from
        `sport_code` (the sport's currently-active default provider), completely ignoring which
        provider `fixture_ref` actually came from — so a fixture reconciled only via
        football-data.org had *its own* numeric external id sent straight to api-sports.io's
        `/fixtures/statistics?fixture={id}` as if it were an api-sports.io fixture id. Live-
        observed as an honest-looking `HTTP 200` with an empty `response` (no api-sports.io
        fixture happens to share that number) — but nothing prevented a numeric collision from
        silently attributing a real, unrelated match's statistics to the wrong fixture. TitanIQ
        has no cross-provider fixture-id mapping (unlike teams, which now go through
        `ProviderRefIndexRepositoryPort`/`_resolve_existing_team`), so the only safe behavior
        today is to refuse the call outright rather than guess. Wraps any fixture_ref-keyed call
        (`fetch_team_statistics`/`fetch_lineups`/`fetch_odds`) so this can never regress
        independently in one of them."""

        def _checked(adapter):
            if adapter.provider_key != fixture_ref.provider:
                raise ProviderNotConfiguredError(
                    f"fixture was reconciled via provider {fixture_ref.provider!r}, but the sport's "
                    f"active adapter is {adapter.provider_key!r} — no cross-provider fixture-id "
                    f"mapping exists, so external id {fixture_ref.external_id!r} cannot safely be "
                    "sent to a different provider's endpoint"
                )
            return call(adapter)

        return _checked

    async def fetch_team_statistics(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderTeamStatisticsRecord]:
        return await self._execute(
            sport_code, ("team_statistics", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, self._guard_same_provider(fixture_ref, lambda adapter: adapter.fetch_team_statistics(fixture_ref)),
        )

    async def fetch_lineups(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderLineupRecord]:
        return await self._execute(
            sport_code, ("lineups", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, self._guard_same_provider(fixture_ref, lambda adapter: adapter.fetch_lineups(fixture_ref)),
        )

    async def fetch_odds(
        self, sport_code: str, fixture_ref: ProviderRef, now: datetime, *, low_priority: bool = True
    ) -> ProviderOddsRecord | None:
        return await self._execute(
            sport_code, ("odds", sport_code, fixture_ref.provider, fixture_ref.external_id),
            now, low_priority, self._guard_same_provider(fixture_ref, lambda adapter: adapter.fetch_odds(fixture_ref)),
        )

    async def fetch_injuries(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *,
        low_priority: bool = False, season_label: str | None = None,
    ) -> list[ProviderInjuryRecord]:
        return await self._execute(
            sport_code, ("injuries", sport_code, team_ref.provider, team_ref.external_id, season_label),
            now, low_priority, lambda adapter: adapter.fetch_injuries(team_ref, season_label),
        )

    async def fetch_transfers(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> list[ProviderTransferRecord]:
        return await self._execute(
            sport_code, ("transfers", sport_code, team_ref.provider, team_ref.external_id),
            now, low_priority, lambda adapter: adapter.fetch_transfers(team_ref),
        )

    async def fetch_coach(
        self, sport_code: str, team_ref: ProviderRef, now: datetime, *, low_priority: bool = False
    ) -> ProviderCoachRecord | None:
        return await self._execute(
            sport_code, ("coach", sport_code, team_ref.provider, team_ref.external_id),
            now, low_priority, lambda adapter: adapter.fetch_coach(team_ref),
        )

    async def _resolve_fixture_schedule_adapter(self, provider_key: str) -> tuple[SportsDataProviderPort, object]:
        adapter = self.fixture_schedule_adapters.get(provider_key)
        if adapter is None:
            raise ProviderNotConfiguredError(f"no fixture-schedule adapter registered for '{provider_key}'")
        provider = await self.admin_service.providers.get_by_key(adapter.provider_key)
        if provider is None or not provider.is_usable():
            raise ProviderNotConfiguredError(f"provider '{provider_key}' is not registered/active")
        credentials = await self.admin_service.usable_credentials(provider.id)
        if not credentials:
            raise ProviderNotConfiguredError(f"provider '{provider_key}' has no usable credential configured")
        return adapter, provider

    async def _execute_fixture_schedule(
        self, cache_key: tuple, provider_key: str, now: datetime, low_priority: bool, resolve_call: callable,
    ):
        """Shared plumbing for `fetch_upcoming_fixtures`/`fetch_standings_alt`/
        `fetch_completed_fixtures` — same cache/lock/circuit/quota/retry behavior as `_execute`,
        just resolved via `_resolve_fixture_schedule_adapter` (no mock fallback: see
        `ProviderNotConfiguredError`) instead of `_resolve_adapter`. `resolve_call(adapter)` picks
        the specific bound method to call (and may itself raise `ProviderNotConfiguredError` for
        a capability the adapter doesn't implement)."""

        async def _fetch():
            adapter, provider = await self._resolve_fixture_schedule_adapter(provider_key)
            call = resolve_call(adapter)
            cache_ttl = _cache_ttl_for(cache_key[0], provider.cache_ttl_seconds if provider else 3600)

            if not self.circuit_breaker.allow_request(adapter.provider_key, now):
                raise ProviderCircuitOpenError(f"circuit open for '{adapter.provider_key}'")
            if provider and await self.quota_engine.should_throttle(provider.id, now, low_priority=low_priority):
                raise ProviderThrottledError(f"quota protection throttled '{adapter.provider_key}'")
            try:
                result = await self._call_with_retry(lambda _adapter: call(), adapter)
            except Exception:
                self.circuit_breaker.record_failure(adapter.provider_key, now)
                if provider:
                    await self.quota_engine.record_request(provider.id, now, success=False)
                raise
            else:
                self.circuit_breaker.record_success(adapter.provider_key)
                if provider:
                    await self.quota_engine.record_request(provider.id, now, success=True)

            await self._cache_set(cache_key, result, cache_ttl)
            return result

        return await self._fetch_with_dedup(cache_key, _fetch)

    async def fetch_upcoming_fixtures(
        self, sport_code: str, provider_key: str, competition_ref: str, season_label: str, now: datetime, *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        """The `fixture_schedule_adapters` counterpart to `fetch_fixtures` — resolves a specific,
        explicitly-opted-into provider (via `provider_key`, looked up by the caller from a
        `CompetitionFixtureSourcePreference`) instead of the sport's default adapter, with no
        mock fallback (see `ProviderNotConfiguredError`). Relies on the resolved adapter's own
        `fetch_fixtures` to have already scoped its request to not-yet-played matches
        (`FootballDataOrgAdapter.fetch_fixtures` does this via its `status=SCHEDULED,TIMED`
        request param) — this method does not re-filter by status, so a future fixture-schedule
        adapter that doesn't pre-filter would need to do so itself, matching this method's
        contract of "upcoming fixtures only"."""
        cache_key = ("upcoming_fixtures", provider_key, competition_ref, season_label)
        return await self._execute_fixture_schedule(
            cache_key, provider_key, now, low_priority,
            lambda adapter: (lambda: adapter.fetch_fixtures(competition_ref, season_label, now)),
        )

    async def fetch_standings_alt(
        self, sport_code: str, provider_key: str, competition_ref: str, season_label: str, now: datetime, *,
        low_priority: bool = False,
    ) -> list[ProviderStandingRecord]:
        """`fetch_upcoming_fixtures`/`fetch_completed_fixtures`'s counterpart for standings — same
        `fixture_schedule_adapters` resolution, circuit-breaker, quota, and caching behavior, but
        calls the adapter's `fetch_standings`. Kept separate from the generic `fetch_standings`
        above (which always resolves the sport's *default* adapter) because a competition's
        `CompetitionFixtureSourcePreference` opts into an explicit alternate provider — mirrors
        `fetch_completed_fixtures`'s "no silent fallback" discipline exactly."""
        cache_key = ("standings_alt", provider_key, competition_ref, season_label)

        def _resolve_call(adapter):
            fetch_standings = getattr(adapter, "fetch_standings", None)
            if fetch_standings is None:
                raise ProviderNotConfiguredError(f"provider '{provider_key}' does not support standings sync")
            return lambda: fetch_standings(competition_ref, season_label)

        return await self._execute_fixture_schedule(cache_key, provider_key, now, low_priority, _resolve_call)

    async def fetch_completed_fixtures(
        self, sport_code: str, provider_key: str, competition_ref: str, season_label: str, now: datetime, *,
        low_priority: bool = False,
    ) -> list[ProviderFixtureRecord]:
        """`fetch_upcoming_fixtures`'s counterpart for final scores — same resolution, circuit-
        breaker, quota, and caching behavior, but calls the adapter's `fetch_completed_fixtures`
        instead. Not every `fixture_schedule_adapters` entry necessarily implements this (it's
        not part of `SportsDataProviderPort`), so a missing method raises `ProviderNotConfiguredError`
        rather than an opaque `AttributeError`, matching this router's existing "no silent
        fallback" discipline for provider-specific capabilities."""
        cache_key = ("completed_fixtures", provider_key, competition_ref, season_label)

        def _resolve_call(adapter):
            fetch_completed = getattr(adapter, "fetch_completed_fixtures", None)
            if fetch_completed is None:
                raise ProviderNotConfiguredError(f"provider '{provider_key}' does not support completed-fixture sync")
            return lambda: fetch_completed(competition_ref, season_label, now)

        return await self._execute_fixture_schedule(cache_key, provider_key, now, low_priority, _resolve_call)
