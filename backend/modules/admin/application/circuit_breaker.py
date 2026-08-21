"""Per-provider circuit breaker (docs/admin_center.md §2).

Deliberately in-memory/per-process rather than DB-backed: circuit state is a short-lived
operational signal ("stop hammering a provider that's currently failing"), not data anyone
needs to query historically — health history for that is `ProviderHealthCheck`
(docs/admin/domain/entities.py), which *is* persisted. `now` is passed in explicitly for the
same testability reason as QuotaIntelligenceEngine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from modules.admin.domain.value_objects import CircuitState


def _ensure_aware(dt: datetime, reference: datetime) -> datetime:
    """SQLite/aiosqlite drops tzinfo on read-back (docs/decisions.md ADR-007)."""
    if dt.tzinfo is None and reference.tzinfo is not None:
        return dt.replace(tzinfo=reference.tzinfo)
    return dt


@dataclass
class _BreakerState:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    opened_at: datetime | None = None


class ProviderCircuitOpenError(RuntimeError):
    """Raised by callers (e.g. ProviderRouter) when a request is short-circuited."""


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    _states: dict[str, _BreakerState] = field(default_factory=dict)

    def _state_for(self, provider_key: str) -> _BreakerState:
        return self._states.setdefault(provider_key, _BreakerState())

    def allow_request(self, provider_key: str, now: datetime) -> bool:
        state = self._state_for(provider_key)
        if state.state is CircuitState.CLOSED:
            return True
        if state.state is CircuitState.OPEN:
            if state.opened_at is not None:
                opened_at = _ensure_aware(state.opened_at, now)
                aware_now = _ensure_aware(now, opened_at)
                if aware_now - opened_at >= self.recovery_timeout:
                    state.state = CircuitState.HALF_OPEN
                    return True
            return False
        return True  # HALF_OPEN: allow exactly one trial request through

    def record_success(self, provider_key: str) -> None:
        state = self._state_for(provider_key)
        state.state = CircuitState.CLOSED
        state.consecutive_failures = 0
        state.opened_at = None

    def record_failure(self, provider_key: str, now: datetime) -> None:
        state = self._state_for(provider_key)
        if state.state is CircuitState.HALF_OPEN:
            state.state = CircuitState.OPEN
            state.opened_at = now
            return
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.failure_threshold:
            state.state = CircuitState.OPEN
            state.opened_at = now

    def state_of(self, provider_key: str) -> CircuitState:
        return self._state_for(provider_key).state
