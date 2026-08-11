"""One-off local dev helper: backfills real `team_statistics` for a bounded sample of already-
synced NBA/EuroLeague/MLB/NPB completed fixtures, using `ApiBasketballAdapter`/`ApiBaseballAdapter`
now that both have been fixed to parse their real (verified live) response shapes instead of a
best-effort guess (2026-08-10 audit fix — see api_sports_adapter.py).

Two hard constraints, both verified live rather than assumed:
1. Each API's own /status endpoint reports a 100 requests/day cap on this free-tier account, a
   SEPARATE quota pool per API (not shared with api_football). MAX_PER_COMPETITION below stays
   well under each day's remaining budget rather than looping over every completed fixture
   (1,708 basketball + 3,923 baseball) in one run.
2. The first run of this script (2026-08-10, no throttling) discovered a second, tighter
   constraint the /status payload doesn't advertise: a real 10-requests-per-minute rate limit.
   Firing requests back-to-back got 429-equivalent rejections that tripped the in-memory
   CircuitBreaker after 5 consecutive failures, short-circuiting everything after — 30/130
   fixtures backfilled, 100 failed. Rate-limited attempts did NOT consume daily quota (confirmed
   by re-checking /status), so this run's throttle (`REQUEST_INTERVAL_SECONDS`) is the actual
   fix, not a daily-budget adjustment. This run also skips fixtures the first run already
   succeeded on, rather than re-spending quota re-fetching them.

Usage: TITANIQ_DB_URL=sqlite+aiosqlite:///./dev.db python scripts/backfill_secondary_sport_statistics.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import build_sync_orchestrator, get_engine
from modules.sports.domain.value_objects import ProviderRef

REQUEST_INTERVAL_SECONDS = 7.0  # 60/7 ≈ 8.6 req/min, safely under the real 10/min cap

TARGETS = (
    # (sport_code, competition name, provider_key, max fixtures to backfill this run)
    ("basketball", "NBA", "api_basketball", 20),
    ("basketball", "EuroLeague", "api_basketball", 20),
    ("baseball", "MLB", "api_baseball", 30),
    ("baseball", "NPB", "api_baseball", 30),
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        now = datetime.now(timezone.utc)
        orchestrator = build_sync_orchestrator(session)

        grand_total = {"attempted": 0, "succeeded": 0, "failed": 0}
        for sport_code, competition_name, provider_key, max_fixtures in TARGETS:
            # Skip fixtures already carrying real team_statistics from the first (partial) run —
            # a fixture has one via its Match row (get_or_create_match keys team_statistics off
            # match_id, not fixture_id directly).
            rows = (
                await session.execute(
                    text(
                        "SELECT f.id, f.provider_ref FROM fixtures f "
                        "JOIN seasons se ON f.season_id = se.id "
                        "JOIN competitions c ON se.competition_id = c.id "
                        "WHERE c.name = :name AND f.status = 'completed' "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM matches m JOIN team_statistics ts ON ts.match_id = m.id "
                        "  WHERE m.fixture_id = f.id"
                        ") "
                        "ORDER BY f.scheduled_at DESC LIMIT :limit"
                    ),
                    {"name": competition_name, "limit": max_fixtures},
                )
            ).all()

            succeeded = 0
            failed = 0
            for i, (raw_fixture_id, provider_ref_json) in enumerate(rows, start=1):
                external_id = json.loads(provider_ref_json)[provider_key]
                fixture_ref = ProviderRef(provider=provider_key, external_id=external_id)
                try:
                    run = await orchestrator.sync_team_statistics_for_fixture(
                        sport_code, fixture_ref, raw_fixture_id, now, force=True
                    )
                    if run is not None and run.status.value in ("succeeded", "partial"):
                        succeeded += 1
                    else:
                        failed += 1
                        print(f"  [{competition_name}] fixture {i}/{len(rows)}: run status={run.status.value if run else None} error={run.error_message if run else None}")
                except Exception as exc:  # noqa: BLE001 — diagnostic backfill script
                    failed += 1
                    print(f"  [{competition_name}] fixture {i}/{len(rows)} error: {exc}")
                if i % 5 == 0 or i == len(rows):
                    print(f"[{competition_name}] {i}/{len(rows)} processed ({succeeded} ok, {failed} failed)", flush=True)
                if i < len(rows):
                    await asyncio.sleep(REQUEST_INTERVAL_SECONDS)

            grand_total["attempted"] += len(rows)
            grand_total["succeeded"] += succeeded
            grand_total["failed"] += failed
            print(f"=== {competition_name}: {succeeded}/{len(rows)} succeeded ===\n")
            await session.commit()

        print(f"TOTAL: {grand_total['succeeded']}/{grand_total['attempted']} fixtures backfilled with real team_statistics")


if __name__ == "__main__":
    asyncio.run(main())
