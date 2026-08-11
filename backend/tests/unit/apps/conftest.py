"""Shared fixtures for apps/api router tests.

`apps.api.rate_limit` reuses the real Redis client (`apps.api.composition.get_redis_client`),
which has a 2s connect/socket timeout (see `build_redis_client`'s docstring). Dozens of these
test files call `/auth/register` or `/auth/login` — often many times per file — and this
environment has no local Redis running. Without this fixture every one of those calls would
eat a real 2s timeout before rate_limit.py's fail-open path kicks in, turning the full suite
into a many-minute run. Autouse + directory-scoped so no individual test file needs to know
about rate limiting at all.
"""

import fakeredis
import pytest

import apps.api.rate_limit as rate_limit_module


@pytest.fixture(autouse=True)
def _fake_redis_for_rate_limit(monkeypatch):
    fake_client = fakeredis.FakeAsyncRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_module, "get_redis_client", lambda: fake_client)
