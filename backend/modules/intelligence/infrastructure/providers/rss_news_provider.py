"""Real RSS/Atom feed adapter for `NewsProviderPort` — genuine HTTP-calling code (no paid API
key required, unlike the sports data providers), covering the "RSS Feeds" source category from
Milestone 8's NEWS INGESTION spec. Parses both RSS 2.0 (`<item>`) and Atom (`<entry>`) feeds with
the standard library's `xml.etree.ElementTree` rather than adding a new feed-parsing dependency.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from modules.intelligence.ports.news_provider import RawArticleRecord

_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class RssFeedError(RuntimeError):
    pass


def _parse_date(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return parsedate_to_datetime(raw)  # RSS 2.0 RFC-822 pubDate
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))  # Atom ISO-8601 updated
    except ValueError:
        return datetime.now(timezone.utc)


def _parse_rss_items(root: ET.Element) -> list[RawArticleRecord]:
    records = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        records.append(
            RawArticleRecord(
                external_ref=link or title,
                title=title,
                url=link,
                body=description,
                published_at=_parse_date(item.findtext("pubDate")),
                author=item.findtext("author"),
            )
        )
    return records


def _parse_atom_entries(root: ET.Element) -> list[RawArticleRecord]:
    records = []
    for entry in root.findall("atom:entry", _ATOM_NS):
        title = (entry.findtext("atom:title", namespaces=_ATOM_NS) or "").strip()
        link_el = entry.find("atom:link", _ATOM_NS)
        link = link_el.get("href", "") if link_el is not None else ""
        summary = (entry.findtext("atom:summary", namespaces=_ATOM_NS) or "").strip()
        records.append(
            RawArticleRecord(
                external_ref=link or title,
                title=title,
                url=link,
                body=summary,
                published_at=_parse_date(entry.findtext("atom:updated", namespaces=_ATOM_NS)),
            )
        )
    return records


class RssNewsProvider:
    provider_key = "rss"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def fetch_articles(
        self, source_url: str, since: datetime | None = None, cursor: str | None = None
    ) -> list[RawArticleRecord]:
        try:
            response = await self._client.get(source_url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except (httpx.HTTPError, ET.ParseError) as exc:
            raise RssFeedError(f"Failed to fetch/parse feed at {source_url}: {exc}") from exc

        records = _parse_rss_items(root) if root.find(".//item") is not None else _parse_atom_entries(root)
        if since is None:
            return records
        return [r for r in records if r.published_at > since]

    async def aclose(self) -> None:
        await self._client.aclose()
