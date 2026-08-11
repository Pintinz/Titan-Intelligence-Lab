"""Fixed-window rate limiting for the small set of endpoints that are either unauthenticated
(so the only throttle available is IP-based) or expensive enough that even an authenticated
free-tier user should not be able to call them without limit (Milestone: Enterprise Security &
Compliance, Phase 11).

No dedicated rate-limiting library exists in this codebase and none is added here — Redis is
already a required dependency (`modules.features.infrastructure.online.redis_feature_store`), so
this reuses that same client via `INCR`+`EXPIRE`, the standard fixed-window counter pattern.
Redis being unreachable fails OPEN (the request proceeds unthrottled) rather than closed — the
same "degrade gracefully, don't take an outage on a cache" posture `RedisFeatureStore` already
uses for feature reads/writes; an unavailable rate limiter should never itself become an outage.

This app has no separate machine/service-credential auth tier: background ingestion runs via
Celery tasks calling `SyncOrchestrator` in-process, never over HTTP against its own API, so there
is no "trusted worker" caller of these endpoints to exempt.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from apps.api.auth_deps import get_current_user
from apps.api.composition import get_redis_client
from modules.identity.domain.entities import User


async def _enforce(request: Request, identity: str | None, key_prefix: str, limit: int, window_seconds: int) -> None:
    if identity is None:
        return
    key = f"ratelimit:{key_prefix}:{identity}"
    client = get_redis_client()
    try:
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
    except Exception:
        return  # Redis unreachable — fail open, never block real traffic on a cache outage.
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests — limit is {limit} per {window_seconds}s. Try again shortly.",
        )


def rate_limit_by_ip(key_prefix: str, limit: int, window_seconds: int):
    """For unauthenticated endpoints (login, register) — the only identity available. No
    reverse-proxy `X-Forwarded-For` trust chain is configured anywhere in this deployment
    (confirmed absent in main.py), so trusting a client-supplied header here would let the limit
    be trivially bypassed by spoofing a new value per request; `request.client.host` (the actual
    TCP peer) is the only source used."""

    async def _dependency(request: Request) -> None:
        identity = request.client.host if request.client else None
        await _enforce(request, identity, key_prefix, limit, window_seconds)

    return _dependency


def rate_limit_by_user(key_prefix: str, limit: int, window_seconds: int):
    """For authenticated, expensive endpoints (e.g. prediction generation) — throttles per user
    id rather than per IP, so one account can't be starved by someone else's traffic and a NAT'd
    office of legitimate users isn't collectively throttled as one IP. Depends on
    `get_current_user` itself so a 401 never consumes a bucket slot; FastAPI dependency-caches
    that call within the request, so the route's own `Depends(get_current_user)` doesn't re-run
    auth a second time."""

    async def _dependency(request: Request, user: User = Depends(get_current_user)) -> None:
        await _enforce(request, str(user.id), key_prefix, limit, window_seconds)

    return _dependency
