"""POST-M24 Phase 8 — `WebHistoricalSource` tests. Pure unit tests (fake `http_get`, real
filesystem cache dir under a pytest tmp_path) — no real network access in the test suite, per the
phase's own "prefer mocks/cached responses" testing rule."""

from __future__ import annotations

import os

import pytest

from modules.ingestion.infrastructure.historical.csv_historical_source import CsvColumnMapping, CsvHistoricalSource
from modules.ingestion.infrastructure.historical.web_historical_source import (
    WebHistoricalSource,
    WebSourceCatalogEntry,
    WebSourceLicense,
)
from modules.sports.domain.value_objects import SportCode

SAMPLE_CSV = (
    "Date,HomeTeam,AwayTeam,FTHG,FTAG\n"
    "05/08/2023,Accrington,Newport County,3,0\n"
    "05/08/2023,Crawley Town,Bradford,1,0\n"
)


def _make_source(tmp_path, http_get=None, source_key="web:test:E3:2324") -> WebHistoricalSource:
    csv_source = CsvHistoricalSource(
        source_key=source_key, sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(
            date="Date", home_team="HomeTeam", away_team="AwayTeam",
            home_score="FTHG", away_score="FTAG", date_format="%d/%m/%Y",
        ),
        default_competition_ref="E3", default_competition_name="English Football League Two",
    )
    return WebHistoricalSource(
        source_key=source_key, url="https://example.test/E3.csv", csv_source=csv_source,
        license=WebSourceLicense(
            basis="site states data is free to use", source_url="https://example.test/notes.txt",
            attribution_note="Data sourced from example.test",
        ),
        cache_dir=str(tmp_path),
        http_get=http_get or (lambda url: SAMPLE_CSV.encode("utf-8")),
    )


def test_source_key_must_match_csv_source_source_key(tmp_path):
    csv_source = CsvHistoricalSource(
        source_key="mismatched", sport=SportCode.FOOTBALL,
        columns=CsvColumnMapping(date="Date", home_team="HomeTeam", away_team="AwayTeam", home_score="FTHG", away_score="FTAG"),
        default_competition_ref="E3", default_competition_name="League Two",
    )
    with pytest.raises(ValueError, match="must match"):
        WebHistoricalSource(
            source_key="web:test", url="https://example.test/x.csv", csv_source=csv_source,
            license=WebSourceLicense(basis="x", source_url="https://example.test", attribution_note="x"),
            cache_dir=str(tmp_path),
        )


def test_fetch_makes_exactly_one_real_request_on_a_cache_miss(tmp_path):
    calls = []
    source = _make_source(tmp_path, http_get=lambda url: (calls.append(url), SAMPLE_CSV.encode())[1])

    path = source.fetch()

    assert len(calls) == 1
    assert calls[0] == "https://example.test/E3.csv"
    assert source.fetched_from_network is True
    assert os.path.exists(path)


def test_fetch_is_a_cache_hit_on_the_second_call_no_further_network_request(tmp_path):
    calls = []
    source = _make_source(tmp_path, http_get=lambda url: (calls.append(url), SAMPLE_CSV.encode())[1])

    source.fetch()
    source.fetch()

    assert len(calls) == 1  # never fetched twice
    assert source.fetched_from_network is False  # the second call was a genuine cache hit


def test_fetch_never_touches_the_network_when_the_cache_file_already_exists_on_disk(tmp_path):
    """Simulates a pre-seeded cache (e.g. this phase's own real-fixture run, which pre-populated
    the cache directory before invoking the pipeline) — the source must never re-fetch."""
    cache_path = os.path.join(str(tmp_path), "web_test_E3_2324.csv")
    with open(cache_path, "w", encoding="utf-8") as fh:
        fh.write(SAMPLE_CSV)
    calls = []
    source = _make_source(tmp_path, http_get=lambda url: calls.append(url) or SAMPLE_CSV.encode())

    path = source.fetch()

    assert len(calls) == 0
    assert source.fetched_from_network is False
    assert path == cache_path


def test_read_records_delegates_to_the_composed_csv_source(tmp_path):
    source = _make_source(tmp_path)
    path = source.fetch()

    result = source.read_records(path)

    assert len(result.records) == 2
    assert result.records[0].home_team_name == "Accrington"
    assert result.records[0].source_key == "web:test:E3:2324"
    assert result.records[0].away_score == 0


def test_web_source_catalog_entry_records_a_rejected_candidate_without_importing_it():
    """Phase 8 Step 3/5 — evaluating and rejecting a candidate source is itself a real, documented
    outcome, not merely a placeholder for approved sources."""
    entry = WebSourceCatalogEntry(
        source_id="basketball_reference", source_name="Basketball-Reference.com", sport="basketball",
        league="NBA", url="https://www.basketball-reference.com", access_method="robots-restricted",
        license_basis="unclear — ToS restricts bulk scraping/redistribution",
        reliability_note="high-quality data, but access is gated",
        update_frequency="n/a — not imported", scraping_required=True,
        rate_limit_note="robots.txt disallows player gamelogs/splits/on-off/lineup data outright",
        attribution_requirement="unclear", approved=False,
        rejection_reason="robots.txt explicitly disallows the exact player-statistics paths this "
        "phase would need; ToS licensing basis for bulk reuse is unclear",
    )

    assert entry.approved is False
    assert entry.rejection_reason is not None
