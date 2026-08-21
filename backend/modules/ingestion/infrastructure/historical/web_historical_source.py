"""POST-M24 Phase 8 — `WebHistoricalSource`: the "web" leg of `HistoricalSourcePort`, alongside
the existing `CsvHistoricalSource` (Phase 4). Deliberately not a new parser and not a new import
pipeline: `HistoricalSourcePort.read_records(file_path)` already reads from a *local file path* —
this class's entire real job is turning a public web URL into that local file path, exactly once,
caching the result on disk so a second call never re-fetches. Parsing itself is delegated whole to
a `CsvHistoricalSource` instance (composition, not duplication) — a web-hosted historical CSV has
the exact same row shape a locally-uploaded one does; only how the bytes arrived differs.

Cache design note: the existing Redis-backed `SportsProviderRouter`/`QuotaIntelligenceEngine`/
`CircuitBreaker` stack (Phase 2) is built for a *live-API* access pattern — many small requests
across many fixtures, repeated on a schedule. A historical web source is the opposite shape: one
static file per source, fetched once, ever (the underlying season is already finished; the file's
content will not change). Routing a one-shot file fetch through machinery designed for a
polling/quota-metered live API would be forcing an ill-fitting abstraction onto a fundamentally
different access pattern. The local on-disk cache below — "does the file already exist? if so,
never touch the network again" — is the right-sized mechanism for this access pattern, and it is
strictly *more* conservative than the live-API cache (a live cache eventually expires and
re-fetches; this one never does, since the historical data it names never changes).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable
from urllib.request import Request, urlopen

from modules.ingestion.infrastructure.historical.csv_historical_source import CsvHistoricalSource
from modules.ingestion.ports.historical_source import HistoricalReadResult

_USER_AGENT = "TitanIQ-HistoricalResearch/1.0 (+internal, non-commercial data-fabric enrichment)"


@dataclass(frozen=True)
class WebSourceLicense:
    """Phase 8 Step 8 — retained, never silently discarded, alongside every import this source
    produces. `basis` is deliberately a free-text field, not a claim of a formal SPDX license: not
    every legitimate public sports-data site publishes one (football-data.co.uk, this phase's own
    source, states only "my data is free" — a real, direct statement, but not a formal license
    grant). Recording the exact real wording here, rather than inventing a formal-sounding license
    name, is the honest choice."""

    basis: str
    source_url: str
    attribution_note: str


def _default_http_get(url: str) -> bytes:
    """Real network fetch — stdlib only (no new dependency), a single unconditional GET with an
    identifying User-Agent, exactly once per distinct URL (see `WebHistoricalSource.fetch`'s
    caching). Never used in tests, which always inject a fake."""
    request = Request(url, headers={"User-Agent": _USER_AGENT})
    with urlopen(request, timeout=30) as response:  # noqa: S310 — deliberate, approved-source-only fetch
        return response.read()


@dataclass
class WebHistoricalSource:
    """Implements `HistoricalSourcePort` by composing a cached web fetch with an existing
    `CsvHistoricalSource` parser. `source_key` must match `csv_source.source_key` — both name the
    same historical source; keeping them in sync is the caller's responsibility (enforced by
    `__post_init__`), not duplicated state."""

    source_key: str
    url: str
    csv_source: CsvHistoricalSource
    license: WebSourceLicense
    cache_dir: str
    http_get: Callable[[str], bytes] = field(default=_default_http_get)
    fetched_from_network: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.csv_source.source_key != self.source_key:
            raise ValueError(
                f"WebHistoricalSource.source_key ({self.source_key!r}) must match "
                f"csv_source.source_key ({self.csv_source.source_key!r})"
            )

    def fetch(self) -> str:
        """Returns a local file path, fetching over the network only on a genuine cache miss.
        Idempotent: calling this twice for the same source never issues a second request."""
        os.makedirs(self.cache_dir, exist_ok=True)
        # `source_key` commonly contains ':' (the same provider-namespacing convention
        # `HistoricalImportService` uses, e.g. "historical:web:..."), which is not a valid
        # filename character on Windows — sanitized for the cache filename only, never for the
        # real source_key value used in provider refs.
        safe_name = self.source_key.replace(":", "_")
        cache_path = os.path.join(self.cache_dir, f"{safe_name}.csv")
        if os.path.exists(cache_path):
            self.fetched_from_network = False
            return cache_path
        content = self.http_get(self.url)
        with open(cache_path, "wb") as fh:
            fh.write(content)
        self.fetched_from_network = True
        return cache_path

    def read_records(self, file_path: str) -> HistoricalReadResult:
        return self.csv_source.read_records(file_path)


@dataclass(frozen=True)
class WebSourceCatalogEntry:
    """Phase 8 Step 3 — one row of the source catalog. A plain data record, not a live registry:
    evaluating a candidate source (`approved=False`, with `rejection_reason` set) is itself a real,
    documented outcome — this phase's own instruction is "do not import merely because a source
    exists," so a rejected/not-yet-approved entry is as much a deliverable as an approved one."""

    source_id: str
    source_name: str
    sport: str
    league: str
    url: str
    access_method: str  # "public CSV download", "robots-restricted", "ToS-restricted", etc.
    license_basis: str
    reliability_note: str
    update_frequency: str
    scraping_required: bool
    rate_limit_note: str
    attribution_requirement: str
    approved: bool
    rejection_reason: str | None = None
