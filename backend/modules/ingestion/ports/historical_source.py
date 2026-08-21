"""Port for a historical-data source — Kaggle CSV today, any future provider-agnostic historical
importer tomorrow without touching `HistoricalImportService`. Deliberately reads from a *local
file path*, not a URL or a live API: how the file got onto disk (a Kaggle API download, an admin
upload, a manual export) is a separate concern this port does not own — see
`CsvHistoricalSource`'s module docstring for why that boundary matters for Phase 4's credential
safety rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from modules.ingestion.domain.historical_import import HistoricalFixtureRecord, QuarantinedRecord


@dataclass(frozen=True)
class HistoricalReadResult:
    records: tuple[HistoricalFixtureRecord, ...]
    rejected: tuple[QuarantinedRecord, ...] = field(default_factory=tuple)


class HistoricalSourcePort(Protocol):
    source_key: str

    def read_records(self, file_path: str) -> HistoricalReadResult: ...
