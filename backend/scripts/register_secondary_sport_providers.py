"""One-off local dev helper: registers `api_basketball`/`api_baseball` as real, active providers.

Audit finding (2026-08-10): `ApiBasketballAdapter`/`ApiBaseballAdapter` (real, tested HTTP adapters
against v1.basketball.api-sports.io / v1.baseball.api-sports.io) already exist and are already wired
into `SportsProviderRouter`'s `real_adapters` dict — but no `providers` row was ever registered for
either key, so `SportsProviderRouter._resolve_adapter()` always fell back to mock for both sports
(no active credentialed provider to route to).

Empirically verified (not assumed) that API-SPORTS uses one account-wide key across their whole
product line: the same plaintext value already stored for the `api_football` provider was tried
directly against both hosts' `/status` endpoint and authenticated successfully on both (HTTP 200,
`subscription.active: true`, Free plan through 2027-07-15). This script reuses that same verified
value rather than asking for or inventing a new one — it is not a new secret, just the existing
API-Football credential registered a second and third time under the sport-specific provider keys
the router already expects.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/register_secondary_sport_providers.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apps.api.composition import build_provider_management_service, get_session_factory
from modules.admin.domain.value_objects import ProviderCategory

NEW_PROVIDERS = (
    {
        "key": "api_basketball",
        "name": "API-Basketball",
        "base_url": "https://v1.basketball.api-sports.io",
    },
    {
        "key": "api_baseball",
        "name": "API-Baseball",
        "base_url": "https://v1.baseball.api-sports.io",
    },
)


async def main() -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        admin_service = build_provider_management_service(session)

        football_provider = await admin_service.providers.get_by_key("api_football")
        football_credentials = await admin_service.usable_credentials(football_provider.id)
        shared_key = await admin_service.reveal_plaintext(football_credentials[0].id)

        for spec in NEW_PROVIDERS:
            existing = await admin_service.providers.get_by_key(spec["key"])
            if existing is not None:
                print(f"{spec['key']}: already registered, skipping")
                continue

            provider = await admin_service.register_provider(
                key=spec["key"],
                name=spec["name"],
                category=ProviderCategory.SPORTS_DATA,
                base_url=spec["base_url"],
                auth_type="api_key",
                auth_header_name="x-apisports-key",
                created_by="seed-script",
            )
            await admin_service.add_credential(provider.id, "primary", shared_key, now=now)
            await admin_service.activate(provider.id)
            print(f"{spec['key']}: registered + credentialed + activated ({provider.id})")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
