"""Generic CSV-based `HistoricalSourcePort` implementation. Deliberately not called
`KaggleHistoricalSource` or anything Kaggle-specific: Kaggle is one *distributor* of CSVs, not an
architecture. This class only ever reads a local file path handed to it — it has no knowledge of
Kaggle's API, credentials, or download mechanism at all.

That boundary is the Phase 4 credential-safety answer: getting a file *onto disk* (via
`kaggle datasets download`, an admin upload, or any other route) is out of scope for this codebase
today because no Kaggle API credentials are configured in this environment (`KAGGLE_USERNAME`/
`KAGGLE_KEY` — checked, both unset; see the Phase 4 verification report's blocked-download
section). This class starts one step later, at "a CSV file already exists at this path" — which is
exactly the part that can be built and tested without ever touching Kaggle's authentication.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone

from modules.ingestion.domain.historical_import import (
    HistoricalFixtureRecord,
    HistoricalOddsQuote,
    HistoricalTeamStatistics,
    QuarantinedRecord,
    QuarantineReason,
)
from modules.ingestion.ports.historical_source import HistoricalReadResult
from modules.sports.domain.value_objects import LineSelection, MarketLineType, SportCode


@dataclass(frozen=True)
class OddsColumnMapping:
    """One real bookmaker's (or provider-reported aggregate's) odds columns for the two markets
    this platform already has real, production markets for — moneyline (three-way) and total
    over/under. Deliberately narrow, not a generic arbitrary-market importer: inventing column
    names for a market nothing in `market_outcome_registry.py` consumes yet would be speculative
    structure, not a real requirement (POST-M24 Phase 12 audit). A source with no odds coverage
    simply omits `odds` on its `CsvColumnMapping` entirely — every existing call site's default."""

    bookmaker: str  # the real name this column set's quotes are attributed to, e.g. "Bet365", "Max", "Avg"
    moneyline_home: str | None = None
    moneyline_draw: str | None = None
    moneyline_away: str | None = None
    total_line: float | None = None  # the real threshold the total_over/total_under columns quote, e.g. 2.5
    total_over: str | None = None
    total_under: str | None = None


@dataclass(frozen=True)
class StatisticsColumnMapping:
    """Which CSV columns carry each side's real match statistics — keyed by the same stat_set
    vocabulary the existing rolling-form-differential calculators already read
    (`_ADDITIONAL_FOOTBALL_STAT_KEYS` in `windowed_feature_engineering_service.py`:
    shots_on_target, shots_total, corners, fouls, cards_yellow). A field left `None` means that
    source genuinely doesn't report that stat — never fabricated, never defaulted to 0."""

    home_shots_on_target: str | None = None
    away_shots_on_target: str | None = None
    home_shots_total: str | None = None
    away_shots_total: str | None = None
    home_corners: str | None = None
    away_corners: str | None = None
    home_fouls: str | None = None
    away_fouls: str | None = None
    home_cards_yellow: str | None = None
    away_cards_yellow: str | None = None


@dataclass(frozen=True)
class CsvColumnMapping:
    """Which CSV header names carry which fields — Kaggle football/basketball/baseball datasets
    each use their own header vocabulary (confirmed live for the football candidate: `date`,
    `home_team`, `away_team`, `home_score`, `away_score`, `tournament` — see
    docs/post_m24_master_data_fabric_phase4_verification_report.md §4), so this is configuration,
    not a hardcoded assumption about any one dataset's schema."""

    date: str
    home_team: str
    away_team: str
    home_score: str
    away_score: str
    competition: str | None = None  # None -> every row uses default_competition_ref/name below
    date_format: str = "%Y-%m-%d"
    odds: tuple[OddsColumnMapping, ...] = ()  # real historical bookmaker quotes, when the source carries them
    statistics: StatisticsColumnMapping | None = None  # real per-side match stats, when the source carries them


@dataclass
class CsvHistoricalSource:
    source_key: str
    sport: SportCode
    columns: CsvColumnMapping
    default_competition_ref: str
    default_competition_name: str

    def read_records(self, file_path: str) -> HistoricalReadResult:
        records: list[HistoricalFixtureRecord] = []
        rejected: list[QuarantinedRecord] = []
        with open(file_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row_index, row in enumerate(reader):
                source_record_id = f"{self.source_key}:{row_index}"
                record = self._parse_row(row, source_record_id)
                if record is None:
                    rejected.append(
                        QuarantinedRecord(
                            source_record_id=source_record_id,
                            reason=QuarantineReason.UNPARSEABLE_ROW,
                            detail=f"row {row_index}: missing or unparseable required field",
                        )
                    )
                    continue
                records.append(record)
        return HistoricalReadResult(records=tuple(records), rejected=tuple(rejected))

    def _parse_row(self, row: dict, source_record_id: str) -> HistoricalFixtureRecord | None:
        home_team = (row.get(self.columns.home_team) or "").strip()
        away_team = (row.get(self.columns.away_team) or "").strip()
        raw_date = (row.get(self.columns.date) or "").strip()
        if not home_team or not away_team or not raw_date:
            return None
        try:
            scheduled_at = datetime.strptime(raw_date, self.columns.date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            return None
        home_score = self._parse_int(row.get(self.columns.home_score))
        away_score = self._parse_int(row.get(self.columns.away_score))
        competition_ref = self.default_competition_ref
        competition_name = self.default_competition_name
        if self.columns.competition and row.get(self.columns.competition):
            raw_competition = row[self.columns.competition].strip()
            if raw_competition:
                competition_ref = raw_competition
                competition_name = raw_competition
        home_statistics, away_statistics = self._parse_statistics(row)
        return HistoricalFixtureRecord(
            source_key=self.source_key,
            source_record_id=source_record_id,
            sport=self.sport,
            competition_ref=competition_ref,
            competition_name=competition_name,
            odds=self._parse_odds(row),
            season_label=str(scheduled_at.year),
            scheduled_at=scheduled_at,
            home_team_name=home_team,
            away_team_name=away_team,
            home_score=home_score,
            away_score=away_score,
            home_statistics=home_statistics,
            away_statistics=away_statistics,
        )

    def _parse_statistics(
        self, row: dict
    ) -> tuple[HistoricalTeamStatistics | None, HistoricalTeamStatistics | None]:
        mapping = self.columns.statistics
        if mapping is None:
            return None, None
        home_set: dict = {}
        away_set: dict = {}
        for stat_key, home_col, away_col in (
            ("shots_on_target", mapping.home_shots_on_target, mapping.away_shots_on_target),
            ("shots_total", mapping.home_shots_total, mapping.away_shots_total),
            ("corners", mapping.home_corners, mapping.away_corners),
            ("fouls", mapping.home_fouls, mapping.away_fouls),
            ("cards_yellow", mapping.home_cards_yellow, mapping.away_cards_yellow),
        ):
            home_value = self._parse_int(row.get(home_col)) if home_col else None
            if home_value is not None:
                home_set[stat_key] = home_value
            away_value = self._parse_int(row.get(away_col)) if away_col else None
            if away_value is not None:
                away_set[stat_key] = away_value
        home_stats = HistoricalTeamStatistics(stat_set=home_set) if home_set else None
        away_stats = HistoricalTeamStatistics(stat_set=away_set) if away_set else None
        return home_stats, away_stats

    def _parse_odds(self, row: dict) -> tuple[HistoricalOddsQuote, ...]:
        quotes: list[HistoricalOddsQuote] = []
        for mapping in self.columns.odds:
            home_price = self._parse_price(row.get(mapping.moneyline_home)) if mapping.moneyline_home else None
            draw_price = self._parse_price(row.get(mapping.moneyline_draw)) if mapping.moneyline_draw else None
            away_price = self._parse_price(row.get(mapping.moneyline_away)) if mapping.moneyline_away else None
            for price, selection in (
                (home_price, LineSelection.HOME), (draw_price, LineSelection.DRAW), (away_price, LineSelection.AWAY),
            ):
                if price is not None:
                    quotes.append(HistoricalOddsQuote(
                        bookmaker=mapping.bookmaker, market_type=MarketLineType.MONEYLINE.value,
                        selection=selection.value, line=None, price=price,
                    ))

            over_price = self._parse_price(row.get(mapping.total_over)) if mapping.total_over else None
            under_price = self._parse_price(row.get(mapping.total_under)) if mapping.total_under else None
            for price, selection in ((over_price, LineSelection.OVER), (under_price, LineSelection.UNDER)):
                if price is not None:
                    quotes.append(HistoricalOddsQuote(
                        bookmaker=mapping.bookmaker, market_type=MarketLineType.TOTAL.value,
                        selection=selection.value, line=mapping.total_line, price=price,
                    ))
        return tuple(quotes)

    @staticmethod
    def _parse_price(raw: str | None) -> float | None:
        """A real decimal sportsbook price is always > 1.0 — a blank column, a stray "-"/"0" the
        source sometimes uses for "no quote", or an unparseable value all mean "no real quote
        here," never a fabricated 0.0 or 1.0 price."""
        if raw is None or raw.strip() == "":
            return None
        try:
            price = float(raw)
        except ValueError:
            return None
        return price if price > 1.0 else None

    @staticmethod
    def _parse_int(raw: str | None) -> int | None:
        if raw is None or raw.strip() == "":
            return None
        try:
            return int(float(raw))
        except ValueError:
            return None
