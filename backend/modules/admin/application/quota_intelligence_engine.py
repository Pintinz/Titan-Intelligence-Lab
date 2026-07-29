"""API Quota Intelligence Engine (docs/admin_center.md §2 "Rate Limit Intelligence").

Tracks per-provider (and per-credential) request usage across daily/monthly windows, predicts
exhaustion, decides whether a request should be throttled, and picks which credential to use
next. `now` is always passed in explicitly rather than read from the clock internally, so this
class is deterministically testable and safe to call from anywhere without hidden global state.

Window rollover is implicit: a new calendar day/month produces a new `window_key`, which is a
fresh `ProviderUsageRecord` with zero usage — "automatically resume synchronization when quotas
reset" falls out of that naturally rather than needing an explicit reset job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from modules.admin.domain.entities import ProviderCredential, ProviderUsageRecord
from modules.admin.domain.value_objects import CredentialId, ProviderId, QuotaPeriod
from modules.admin.ports.repositories import ProviderRepositoryPort, UsageRepositoryPort

# Below this fraction of remaining quota, admins should be alerted and low-priority work throttled.
ALERT_THRESHOLD = 0.15
THROTTLE_THRESHOLD = 0.10


def _daily_window_key(now: datetime) -> str:
    return now.date().isoformat()


def _monthly_window_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


@dataclass
class QuotaSnapshot:
    used: int
    limit: int | None
    remaining: int | None  # None when the provider has no configured limit (unbounded)

    @property
    def remaining_ratio(self) -> float | None:
        if self.limit is None or self.limit == 0:
            return None
        return max(0.0, (self.limit - self.used) / self.limit)


@dataclass
class QuotaIntelligenceEngine:
    providers: ProviderRepositoryPort
    usage: UsageRepositoryPort

    async def record_request(
        self,
        provider_id: ProviderId,
        now: datetime,
        success: bool,
        credential_id: CredentialId | None = None,
    ) -> None:
        for period, window_key in (
            (QuotaPeriod.DAILY, _daily_window_key(now)),
            (QuotaPeriod.MONTHLY, _monthly_window_key(now)),
        ):
            record = await self.usage.get(provider_id, period, window_key, credential_id)
            if record is None:
                record = ProviderUsageRecord(
                    provider_id=provider_id,
                    period=period,
                    window_key=window_key,
                    credential_id=credential_id,
                )
            record.request_count += 1
            if not success:
                record.error_count += 1
            await self.usage.upsert(record)

    async def snapshot(
        self, provider_id: ProviderId, period: QuotaPeriod, now: datetime
    ) -> QuotaSnapshot:
        provider = await self.providers.get(provider_id)
        limit = (
            provider.daily_quota_limit if period is QuotaPeriod.DAILY else provider.monthly_quota_limit
        ) if provider else None
        window_key = _daily_window_key(now) if period is QuotaPeriod.DAILY else _monthly_window_key(now)
        record = await self.usage.get(provider_id, period, window_key)
        used = record.request_count if record else 0
        remaining = None if limit is None else max(0, limit - used)
        return QuotaSnapshot(used=used, limit=limit, remaining=remaining)

    async def predict_daily_exhaustion_hour(
        self, provider_id: ProviderId, now: datetime
    ) -> float | None:
        """Linear projection: at the current hourly consumption rate, how many hours from
        midnight until the daily quota is exhausted? Returns None if unbounded or no usage yet.
        """
        snapshot = await self.snapshot(provider_id, QuotaPeriod.DAILY, now)
        if snapshot.limit is None or snapshot.used == 0:
            return None
        hours_elapsed = max(now.hour + now.minute / 60, 1 / 60)
        rate_per_hour = snapshot.used / hours_elapsed
        if rate_per_hour <= 0:
            return None
        remaining = max(0, snapshot.limit - snapshot.used)
        return hours_elapsed + (remaining / rate_per_hour)

    async def needs_alert(self, provider_id: ProviderId, now: datetime) -> bool:
        snapshot = await self.snapshot(provider_id, QuotaPeriod.DAILY, now)
        ratio = snapshot.remaining_ratio
        return ratio is not None and ratio <= ALERT_THRESHOLD

    async def should_throttle(self, provider_id: ProviderId, now: datetime, *, low_priority: bool) -> bool:
        """Live-priority requests are only throttled once quota is fully exhausted; low-priority
        (background sync) requests are throttled early to protect headroom for live traffic —
        "live data receives higher priority than historical synchronization" (docs/admin_center.md).
        """
        snapshot = await self.snapshot(provider_id, QuotaPeriod.DAILY, now)
        ratio = snapshot.remaining_ratio
        if ratio is None:
            return False
        if low_priority:
            return ratio <= THROTTLE_THRESHOLD
        return ratio <= 0.0

    @staticmethod
    def select_credential(
        credentials: list[ProviderCredential],
        usage_by_credential: dict[CredentialId, int],
        now: datetime,
    ) -> ProviderCredential | None:
        """Picks the usable credential with the lowest usage so far this window — a simple
        load-balancing / automatic-key-switching strategy ("Automatically Switch Between
        Available Keys"). Returns None if every credential is inactive/expired (caller should
        fall back to cached data — "graceful degradation").
        """
        usable = [c for c in credentials if c.is_active and not c.is_expired(now)]
        if not usable:
            return None
        return min(usable, key=lambda c: usage_by_credential.get(c.id, 0))
