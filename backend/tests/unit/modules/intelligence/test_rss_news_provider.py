"""Tests the real RSS/Atom adapter against a mocked transport — the actual adapter code (HTTP
GET, XML parsing, date parsing) runs; only the network is faked (docs/decisions.md ADR-008
pattern, same as tests/unit/modules/sports/test_api_sports_adapter.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from modules.intelligence.infrastructure.providers.rss_news_provider import RssFeedError, RssNewsProvider

_RSS_FEED = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Mock Sports Feed</title>
    <item>
      <title>Striker Signs New Deal</title>
      <link>https://example.com/striker-signs</link>
      <description>The striker has agreed a new long-term contract.</description>
      <pubDate>Sun, 26 Jul 2026 10:00:00 GMT</pubDate>
      <author>staff@example.com</author>
    </item>
    <item>
      <title>Manager Discusses Tactics</title>
      <link>https://example.com/manager-tactics</link>
      <description>The manager spoke about formation changes.</description>
      <pubDate>Mon, 27 Jul 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

_ATOM_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Mock Atom Feed</title>
  <entry>
    <title>Club Announces Partnership</title>
    <link href="https://example.com/partnership" />
    <summary>The club has announced a new partnership deal.</summary>
    <updated>2026-07-26T10:00:00Z</updated>
  </entry>
</feed>
"""


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_articles_parses_rss_items():
    def handler(request):
        return httpx.Response(200, text=_RSS_FEED)

    provider = RssNewsProvider(client=_client_for(handler))

    records = await provider.fetch_articles("https://example.com/feed.xml")

    assert len(records) == 2
    assert records[0].title == "Striker Signs New Deal"
    assert records[0].url == "https://example.com/striker-signs"
    assert records[0].author == "staff@example.com"


@pytest.mark.asyncio
async def test_fetch_articles_parses_atom_entries():
    def handler(request):
        return httpx.Response(200, text=_ATOM_FEED)

    provider = RssNewsProvider(client=_client_for(handler))

    records = await provider.fetch_articles("https://example.com/atom.xml")

    assert len(records) == 1
    assert records[0].title == "Club Announces Partnership"
    assert records[0].url == "https://example.com/partnership"


@pytest.mark.asyncio
async def test_fetch_articles_filters_by_since():
    def handler(request):
        return httpx.Response(200, text=_RSS_FEED)

    provider = RssNewsProvider(client=_client_for(handler))
    since = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)

    records = await provider.fetch_articles("https://example.com/feed.xml", since=since)

    assert len(records) == 1
    assert records[0].title == "Manager Discusses Tactics"


@pytest.mark.asyncio
async def test_fetch_articles_raises_on_http_error():
    def handler(request):
        return httpx.Response(500, text="server error")

    provider = RssNewsProvider(client=_client_for(handler))

    with pytest.raises(RssFeedError):
        await provider.fetch_articles("https://example.com/feed.xml")


@pytest.mark.asyncio
async def test_fetch_articles_raises_on_malformed_xml():
    def handler(request):
        return httpx.Response(200, text="not xml at all <<<")

    provider = RssNewsProvider(client=_client_for(handler))

    with pytest.raises(RssFeedError):
        await provider.fetch_articles("https://example.com/feed.xml")


@pytest.mark.asyncio
async def test_aclose_closes_client():
    closed = {"value": False}

    class TrackingClient(httpx.AsyncClient):
        async def aclose(self):
            closed["value"] = True
            await super().aclose()

    provider = RssNewsProvider(client=TrackingClient(transport=httpx.MockTransport(lambda r: httpx.Response(200))))

    await provider.aclose()

    assert closed["value"] is True
