"""Registers real Premier League-relevant news sources for the existing, already-live RSS
ingestion pipeline (`RssNewsProvider` / `NewsIngestionService.sync_all_sources`).

Audit finding (Premier League data-enrichment work, 2026-08-22): the RSS news pipeline was fully
real and already wired into production (`intelligence.sync_scheduled_news`, Beat-scheduled every
15 minutes for football/EPL via `sync-scheduled-news-football-epl`) — but zero `NewsSource` rows
existed anywhere, for any sport. `sync_all_sources` iterates `self.sources.list_all()`, so a
correctly-wired pipeline with no registered sources simply has nothing to sync every 15 minutes.

Per this project's standing rule against fabricating a source that doesn't genuinely exist: no
"Premier League official API" is registered here (none exists — see the architectural correction
this script's own commit responds to). Both feeds below were verified live before being hardcoded
(`curl`, HTTP 200, real current Premier League match content in the response body, standard RSS
2.0 `<item>` shape `RssNewsProvider._parse_rss_items` already parses) — not assumed from memory.

Idempotent: re-running this is safe — `NewsSource.url` is the identity key
(`SqlAlchemyNewsSourceRepository.get_by_url`), so an existing row is left alone rather than
duplicated.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker

from apps.api.composition import get_engine
from modules.intelligence.domain.entities import NewsSource
from modules.intelligence.domain.value_objects import NewsSourceId, NewsSourceType
from modules.intelligence.infrastructure.persistence.repositories import SqlAlchemyNewsSourceRepository

# Verified live 2026-08-22 (curl, HTTP 200, real current Premier League match content, standard
# RSS 2.0 <item> shape) — not assumed from training data. is_official=False for both: neither is
# published by the Premier League or a club itself, both are established sports-news publishers
# (NewsSourceType.RSS_FEED, not APPROVED_PUBLISHER, since ingestion goes through the generic RSS
# adapter either way — is_official only marks provenance, not the ingestion mechanism).
PREMIER_LEAGUE_NEWS_SOURCES: tuple[tuple[str, str], ...] = (
    ("BBC Sport — Premier League", "https://feeds.bbci.co.uk/sport/football/premier-league/rss.xml"),
    ("The Guardian — Premier League", "https://www.theguardian.com/football/premierleague/rss"),
)


async def main() -> None:
    session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        sources = SqlAlchemyNewsSourceRepository(session=session)
        now = datetime.now(timezone.utc)

        created, existing = 0, 0
        for name, url in PREMIER_LEAGUE_NEWS_SOURCES:
            if await sources.get_by_url(url) is not None:
                existing += 1
                continue
            await sources.upsert(
                NewsSource(
                    id=NewsSourceId(uuid4()), source_type=NewsSourceType.RSS_FEED, name=name, url=url,
                    is_official=False, created_at=now,
                )
            )
            created += 1

        await session.commit()
        print(f"Premier League news sources: {created} created, {existing} already registered.")


if __name__ == "__main__":
    asyncio.run(main())
