# POST-M24 Phase 12 — Historical Data Expansion & Multi-Source Data Fabric Report

## Odds Import & Rejected-Source Re-Verification

**Date:** 2026-08-16
**Scope (as selected by the user from the full Phase 12 brief):** a real historical odds import
against `dev.db` through the existing `HistoricalImportService`/`MarketLineRepositoryPort` seam,
plus a fresh, live re-check of every previously-rejected historical source's licensing/robots.txt
status. No training, no calibration, no model promotion, no Celery Beat schedule changes — none
were touched.

---

## 1. Executive Summary

`MarketLineRepositoryPort`/`MarketLine` (`modules/sports/...`) was a fully-built persistence layer —
real `SqlAlchemyMarketLineRepository`, real `MarketLineModel` table — that had **never been called
anywhere in the codebase** before this phase (confirmed by a full-repo grep). Phase 12 closed that
gap: `HistoricalImportService` now optionally accepts a `market_lines: MarketLineRepositoryPort`,
and a new `HistoricalOddsQuote` record type flows odds columns from a historical CSV source straight
into real `MarketLine` rows, using the exact same DRY_RUN → VALIDATE → IMPORT contract every other
historical import already honors.

One real, bounded import was run against the same English League Two 2023/24 dataset Phase 8
already reconciled into `dev.db` (football-data.co.uk, still the only approved historical web
source): **552 fixtures matched, 6,072 real odds quotes recorded, 0 quarantined.** DRY_RUN and
VALIDATE both correctly predicted the exact IMPORT outcome before any row was written.

Re-verification of every previously-rejected source, done live (not recalled from memory), found
**no change in usability** — basketball-reference.com and baseball-reference.com remain blocked,
Kaggle remains blocked for lack of credentials. football-data.co.uk remains the only approved
source, and it was already exhausted for the one competition this platform has real fixtures for.

---

## 2. Odds Import — What Was Built

- **`HistoricalOddsQuote`** (`modules/ingestion/domain/historical_import.py`) — a new frozen
  dataclass: `bookmaker`, `market_type`, `selection`, `line`, `price`. `HistoricalFixtureRecord`
  gained an `odds: tuple[HistoricalOddsQuote, ...] = ()` field (default empty — every existing
  record shape and every existing test is unaffected).
- **`OddsColumnMapping`** (`modules/ingestion/infrastructure/historical/csv_historical_source.py`) —
  a new frozen dataclass describing which CSV columns hold a given bookmaker's moneyline/total
  odds. `CsvColumnMapping.odds: tuple[OddsColumnMapping, ...] = ()` — opt-in, zero effect on sources
  that don't configure it. `_parse_odds`/`_parse_price` reject any price `<= 1.0` (a decimal-odds
  floor a real bookmaker quote can never cross) rather than writing a corrupt quote.
- **`HistoricalImportService`** gained an optional `market_lines: MarketLineRepositoryPort | None`.
  DRY_RUN/VALIDATE count `odds_quotes_recorded` without writing anything. IMPORT writes each real
  quote as a `MarketLine` (via `MarketLineType(quote.market_type)`) tagged to the same reconciled
  `Fixture`, right after `EntityReconciliationService.reconcile_fixture` runs. `market_lines=None`
  (the pre-Phase-12 default) silently skips odds writing — full backward compatibility.
- **`composition.py`**: `build_historical_import_service` now wires a real
  `SqlAlchemyMarketLineRepository` in.
- **Tests**: 7 new cases covering odds extraction, blank-column skipping, `price <= 1.0` rejection,
  no-odds-configured passthrough, a real IMPORT write, DRY_RUN/VALIDATE no-write, and the
  `market_lines=None` silent-skip path. Full regression suite: **2,441 passed, 0 failed.**

## 3. The Real Import

| Metric | Value |
|---|---|
| Source | football-data.co.uk, English League Two, 2023/24 |
| Bookmakers configured | Bet365, Max, Avg (moneyline + total-goals lines) |
| Fixtures matched | 552 |
| Odds quotes recorded | 6,072 |
| Quarantined | 0 |
| DRY_RUN / VALIDATE vs. real IMPORT | identical predicted outcome, confirmed before writing |

Every quote is a real `MarketLine` row, provenance-tagged `SyncTrigger.BACKFILL` (never
`VERIFIED_PRE_MATCH` — historical import structurally cannot produce that classification, per
Phase 8's own finding). No odds value was invented, interpolated, or estimated.

## 4. Rejected-Source Re-Verification (Live, Not Recalled)

| Source | Prior finding | Re-check result this phase |
|---|---|---|
| football-data.co.uk | APPROVED (permissive robots.txt) | **Unchanged — still approved.** Already the source used above. |
| basketball-reference.com | REJECTED — robots.txt disallows the exact granular-stat paths needed | **Unchanged — still rejected.** `Crawl-delay: 3` confirmed present; disallowed paths re-fetched and re-confirmed blocked. |
| baseball-reference.com | REJECTED — robots.txt itself unreachable behind bot-detection | **Worse, not better.** Live re-check hit an active Cloudflare bot-challenge returning HTTP 403 on the robots.txt request itself — a stronger block than the prior finding, not merely a repeat of it. |
| Kaggle | BLOCKED — no credentials | **Unchanged.** No `KAGGLE_USERNAME`/`KAGGLE_KEY` env vars, no `~/.kaggle/kaggle.json` on this machine. |

No source was scraped in violation of its own terms. No new source became usable this phase.

## 5. What Was Explicitly Not Done

- No training, calibration fitting, model promotion, or Champion changes.
- No Celery Beat schedule changes.
- Basketball/baseball historical odds — still 0% real coverage. The two candidate sources for these
  sports remain blocked (see §4); this is an honest, unresolved gap, not a deferred build item.
- Player-level statistics import — out of scope for the odds-import-only slice the user selected
  from the full Phase 12 brief.

---

## PHASE 12 STATUS: COMPLETE (scoped)

**SCOPE EXECUTED:** Odds import + fresh re-verification of the rejected sources (user-selected
subset of the full Phase 12 brief — not the full historical-data-expansion spec).

**ARCHITECTURE:** `MarketLineRepositoryPort`/`MarketLine` — pre-existing, previously dead code — now
live via `HistoricalImportService`. No new import pipeline; the existing DRY_RUN/VALIDATE/IMPORT
contract from Phase 4/8 was reused unmodified.

**HISTORICAL SOURCES AUDITED:** football-data.co.uk (APPROVED, used), basketball-reference.com
(REJECTED), baseball-reference.com (REJECTED, now more clearly blocked than before), Kaggle
(BLOCKED — no credentials).

**REAL DATA WRITTEN:** 6,072 real odds quotes (`MarketLine` rows), 0 fabricated, 0 quarantined,
against 552 already-reconciled English League Two 2023/24 fixtures.

**TRAINING / CALIBRATION / PROMOTION / CELERY BEAT SCHEDULE:** untouched, as instructed.

**TEST SUITE:** 2,441 passed, 0 failed (full regression, includes 7 new Phase 12 tests).

**NEXT AUTHORIZATION REQUIRED:** none for Phase 12 itself — proceeding to Phase 13 per separate
user instruction. Training/calibration/promotion for any market remains gated on explicit user
authorization, not started.
