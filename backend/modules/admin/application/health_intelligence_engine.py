"""Provider Health Intelligence subsystem (docs/admin_center.md §2, docs/decisions.md
ADR-011/012).

Two data shapes back everything here:
  - ``ProviderHealthCheck`` — append-only history of raw pings, the source of truth for every
    windowed metric (success/failure rate, latency percentiles, uptime, trends).
  - ``ProviderHealthState`` — one materialized row per provider, updated incrementally on every
    ``record_check`` call, so ``consecutive_failures``/current ``status`` are O(1) reads instead
    of rescanning history, and degradation/recovery/incident lifecycle happen automatically as
    checks come in rather than needing a separate "run health scoring" job.

Nothing here calls a provider itself — recording a check is the caller's responsibility
(``SportsProviderRouter`` on every real request, or a dedicated probe for
``attempt_recovery``). This engine only interprets results.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from modules.admin.domain.entities import (
    ProviderHealthCheck,
    ProviderHealthState,
    ProviderIncident,
    ProviderUsageRecord,
)
from modules.admin.domain.value_objects import (
    CredentialId,
    HealthStatus,
    IncidentId,
    IncidentSeverity,
    ProviderId,
    QuotaPeriod,
)
from modules.admin.ports.repositories import (
    HealthRepositoryPort,
    HealthStateRepositoryPort,
    IncidentRepositoryPort,
    UsageRepositoryPort,
)

DAY = timedelta(hours=24)
MONTH = timedelta(days=30)
DEFAULT_RECOVERY_COOLDOWN = timedelta(minutes=5)


@dataclass(frozen=True)
class WindowMetrics:
    """Everything computable from a single set of checks — every windowed method below is a
    thin wrapper: fetch checks for a window, run them through this once."""

    success_rate: float | None
    failure_rate: float | None
    average_latency_ms: float | None
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    check_count: int


@dataclass(frozen=True)
class DailyHealthPoint:
    date: str
    success_rate: float | None
    average_latency_ms: float | None
    check_count: int


@dataclass(frozen=True)
class ProviderDiagnosticsReport:
    provider_id: ProviderId
    status: HealthStatus
    consecutive_failures: int
    reliability_score: float | None
    metrics_24h: WindowMetrics
    daily_uptime: float | None
    monthly_uptime: float | None
    open_incident: ProviderIncident | None
    recent_checks: tuple[ProviderHealthCheck, ...]
    recommendation: str


def _percentile(sorted_values: list[float], p: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _metrics_for_checks(checks: list[ProviderHealthCheck]) -> WindowMetrics:
    if not checks:
        return WindowMetrics(None, None, None, None, None, None, 0)
    successes = sum(1 for c in checks if c.success)
    success_rate = successes / len(checks)
    latencies = sorted(c.latency_ms for c in checks if c.latency_ms is not None)
    average = sum(latencies) / len(latencies) if latencies else None
    return WindowMetrics(
        success_rate=success_rate,
        failure_rate=1 - success_rate,
        average_latency_ms=average,
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        p99_latency_ms=_percentile(latencies, 0.99),
        check_count=len(checks),
    )


@dataclass
class HealthIntelligenceEngine:
    health: HealthRepositoryPort
    health_state: HealthStateRepositoryPort
    incidents: IncidentRepositoryPort
    usage: UsageRepositoryPort
    degraded_threshold: int = 2  # consecutive failures -> DEGRADED
    down_threshold: int = 5  # consecutive failures -> DOWN
    latency_ceiling_ms: float = 2000.0  # latency at/above this scores 0 in reliability_score

    # -- recording & automatic classification -----------------------------------------------

    async def record_check(
        self,
        provider_id: ProviderId,
        now: datetime,
        success: bool,
        latency_ms: float | None = None,
        message: str | None = None,
    ) -> tuple[ProviderHealthCheck, ProviderHealthState]:
        check = ProviderHealthCheck(
            provider_id=provider_id, checked_at=now, success=success, latency_ms=latency_ms, message=message
        )
        await self.health.record(check)

        state = await self.health_state.get(provider_id) or ProviderHealthState(provider_id=provider_id)
        state.last_check_at = now
        if success:
            state.consecutive_successes += 1
            state.consecutive_failures = 0
            state.last_success_at = now
        else:
            state.consecutive_failures += 1
            state.consecutive_successes = 0
            state.last_failure_at = now

        new_status = self._classify(state.consecutive_failures)
        await self._apply_transition(state, new_status, now, message)
        state.status = new_status
        await self.health_state.upsert(state)
        return check, state

    def _classify(self, consecutive_failures: int) -> HealthStatus:
        if consecutive_failures >= self.down_threshold:
            return HealthStatus.DOWN
        if consecutive_failures >= self.degraded_threshold:
            return HealthStatus.DEGRADED
        return HealthStatus.HEALTHY

    async def _apply_transition(
        self, state: ProviderHealthState, new_status: HealthStatus, now: datetime, trigger: str | None
    ) -> None:
        if new_status == state.status:
            return

        if new_status is not HealthStatus.HEALTHY and state.open_incident_id is None:
            incident = ProviderIncident(
                id=IncidentId(uuid4()),
                provider_id=state.provider_id,
                severity=IncidentSeverity.CRITICAL if new_status is HealthStatus.DOWN else IncidentSeverity.WARNING,
                opened_at=now,
                trigger=trigger or f"{state.consecutive_failures} consecutive failures",
            )
            await self.incidents.upsert(incident)
            state.open_incident_id = incident.id
        elif new_status is HealthStatus.DOWN and state.status is HealthStatus.DEGRADED and state.open_incident_id:
            # Escalate the existing incident rather than opening a second one. Severity is a
            # high-water mark — it never downgrades mid-incident, only on resolution.
            incident = await self.incidents.get(state.open_incident_id)
            if incident is not None:
                incident.severity = IncidentSeverity.CRITICAL
                await self.incidents.upsert(incident)
        elif new_status is HealthStatus.HEALTHY and state.open_incident_id is not None:
            incident = await self.incidents.get(state.open_incident_id)
            if incident is not None:
                incident.resolved_at = now
                await self.incidents.upsert(incident)
            state.open_incident_id = None

    # -- point-in-time state ------------------------------------------------------------------

    async def current_status(self, provider_id: ProviderId) -> HealthStatus:
        state = await self.health_state.get(provider_id)
        return state.status if state else HealthStatus.HEALTHY  # no data yet == nothing wrong

    async def consecutive_failures(self, provider_id: ProviderId) -> int:
        state = await self.health_state.get(provider_id)
        return state.consecutive_failures if state else 0

    # -- windowed metrics ----------------------------------------------------------------------

    async def window_metrics(self, provider_id: ProviderId, now: datetime, window: timedelta) -> WindowMetrics:
        checks = await self.health.list_since(provider_id, now - window)
        return _metrics_for_checks(checks)

    async def success_rate(self, provider_id: ProviderId, now: datetime, window: timedelta = DAY) -> float | None:
        return (await self.window_metrics(provider_id, now, window)).success_rate

    async def failure_rate(self, provider_id: ProviderId, now: datetime, window: timedelta = DAY) -> float | None:
        return (await self.window_metrics(provider_id, now, window)).failure_rate

    async def average_latency(self, provider_id: ProviderId, now: datetime, window: timedelta = DAY) -> float | None:
        return (await self.window_metrics(provider_id, now, window)).average_latency_ms

    async def latency_percentiles(
        self, provider_id: ProviderId, now: datetime, window: timedelta = DAY
    ) -> tuple[float | None, float | None, float | None]:
        metrics = await self.window_metrics(provider_id, now, window)
        return metrics.p50_latency_ms, metrics.p95_latency_ms, metrics.p99_latency_ms

    async def availability_percentage(
        self, provider_id: ProviderId, now: datetime, window: timedelta = DAY
    ) -> float | None:
        rate = await self.success_rate(provider_id, now, window)
        return None if rate is None else round(rate * 100, 2)

    async def daily_uptime(self, provider_id: ProviderId, now: datetime) -> float | None:
        return await self.availability_percentage(provider_id, now, DAY)

    async def monthly_uptime(self, provider_id: ProviderId, now: datetime) -> float | None:
        return await self.availability_percentage(provider_id, now, MONTH)

    async def throughput(self, provider_id: ProviderId, period: QuotaPeriod, window_key: str) -> int:
        record: ProviderUsageRecord | None = await self.usage.get(provider_id, period, window_key)
        return record.request_count if record else 0

    # -- scores ----------------------------------------------------------------------------------

    async def reliability_score(self, provider_id: ProviderId, now: datetime) -> float | None:
        """0-100. 60% recent (24h) success rate, 40% latency (linearly scored down to 0 at
        ``latency_ceiling_ms``). Weighted toward success rate because an unreachable provider
        is worse than a slow one, but latency still matters for user-facing responsiveness.
        None when there's no data yet — an absent score, not a fabricated 100."""
        metrics = await self.window_metrics(provider_id, now, DAY)
        if metrics.check_count == 0:
            return None
        latency_component = 1.0
        if metrics.average_latency_ms is not None:
            latency_component = max(0.0, min(1.0, 1 - metrics.average_latency_ms / self.latency_ceiling_ms))
        score = 0.6 * (metrics.success_rate or 0.0) + 0.4 * latency_component
        return round(score * 100, 1)

    async def credential_reliability_score(
        self, provider_id: ProviderId, credential_id: CredentialId, now: datetime
    ) -> float | None:
        """0-100, based on that credential's own DAILY usage record (request/error counts
        tracked per-credential by QuotaIntelligenceEngine) — independent of the provider-level
        score, so a bad key among several good ones is visible instead of averaged away."""
        window_key = now.date().isoformat()
        record = await self.usage.get(provider_id, QuotaPeriod.DAILY, window_key, credential_id)
        if record is None or record.request_count == 0:
            return None
        success_rate = 1 - (record.error_count / record.request_count)
        return round(success_rate * 100, 1)

    # -- trends & diagnostics ---------------------------------------------------------------------

    async def health_trend(self, provider_id: ProviderId, now: datetime, days: int = 7) -> list[DailyHealthPoint]:
        checks = await self.health.list_since(provider_id, now - timedelta(days=days))
        by_day: dict[str, list[ProviderHealthCheck]] = defaultdict(list)
        for check in checks:
            by_day[check.checked_at.date().isoformat()].append(check)

        points = []
        for offset in range(days):
            day = (now - timedelta(days=days - 1 - offset)).date().isoformat()
            metrics = _metrics_for_checks(by_day.get(day, []))
            points.append(
                DailyHealthPoint(
                    date=day,
                    success_rate=metrics.success_rate,
                    average_latency_ms=metrics.average_latency_ms,
                    check_count=metrics.check_count,
                )
            )
        return points

    async def diagnostics(self, provider_id: ProviderId, now: datetime) -> ProviderDiagnosticsReport:
        state = await self.health_state.get(provider_id) or ProviderHealthState(provider_id=provider_id)
        metrics_24h = await self.window_metrics(provider_id, now, DAY)
        recent = await self.health.list_since(provider_id, now - DAY)
        recent_sorted = tuple(sorted(recent, key=lambda c: c.checked_at, reverse=True)[:10])
        open_incident = await self.incidents.get(state.open_incident_id) if state.open_incident_id else None

        return ProviderDiagnosticsReport(
            provider_id=provider_id,
            status=state.status,
            consecutive_failures=state.consecutive_failures,
            reliability_score=await self.reliability_score(provider_id, now),
            metrics_24h=metrics_24h,
            daily_uptime=await self.daily_uptime(provider_id, now),
            monthly_uptime=await self.monthly_uptime(provider_id, now),
            open_incident=open_incident,
            recent_checks=recent_sorted,
            recommendation=self._recommend(state, metrics_24h),
        )

    def _recommend(self, state: ProviderHealthState, metrics_24h: WindowMetrics) -> str:
        if state.status is HealthStatus.DOWN:
            return (
                f"DOWN — {state.consecutive_failures} consecutive failures. "
                "Automatic recovery attempts should be running; investigate if this persists."
            )
        if state.status is HealthStatus.DEGRADED:
            return f"DEGRADED — {state.consecutive_failures} consecutive failures. Monitor closely."
        if metrics_24h.success_rate is not None and metrics_24h.success_rate < 0.98:
            return "Healthy, but 24h success rate is below 98% — worth watching."
        return "Healthy."

    # -- incidents ------------------------------------------------------------------------------

    async def list_incidents(self, provider_id: ProviderId) -> list[ProviderIncident]:
        return await self.incidents.list_by_provider(provider_id)

    async def open_incident(self, provider_id: ProviderId) -> ProviderIncident | None:
        open_incidents = await self.incidents.list_open(provider_id)
        return open_incidents[0] if open_incidents else None

    # -- automatic recovery -----------------------------------------------------------------------

    async def should_attempt_recovery(
        self, provider_id: ProviderId, now: datetime, cooldown: timedelta = DEFAULT_RECOVERY_COOLDOWN
    ) -> bool:
        state = await self.health_state.get(provider_id)
        if state is None or state.status is HealthStatus.HEALTHY:
            return False
        if state.last_check_at is None:
            return True
        return now - state.last_check_at >= cooldown

    async def attempt_recovery(self, provider_id: ProviderId, now: datetime, probe) -> tuple[ProviderHealthCheck, ProviderHealthState]:
        """``probe`` is an async callable ``() -> tuple[bool, float | None]`` (success, latency_ms)
        — a lightweight ping against the real provider. Recording its result through
        ``record_check`` is what flips status back to HEALTHY and resolves the open incident
        once enough consecutive successes land; there's no separate recovery code path to keep
        in sync with the main classification logic. Actual scheduling (calling this
        periodically while a provider is DOWN) is a background-job concern that lands with
        Celery beat wiring in a later milestone — this method is what that job would call."""
        success, latency_ms = await probe()
        return await self.record_check(provider_id, now, success, latency_ms=latency_ms, message="recovery attempt")
