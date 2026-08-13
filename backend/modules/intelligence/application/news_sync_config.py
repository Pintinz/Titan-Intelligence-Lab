"""Milestone 10 — Scheduled News Sync configuration. Same "local `_env_int`/`_env_bool` helper,
duplicated per module rather than shared" posture every prior module-boundary-respecting constant
in this codebase already uses (`modules.ingestion.application.provenance.LINEUP_PREMATCH_WINDOW_MINUTES`,
`modules.intelligence.application.news_validity_policy._VALIDITY_WINDOW_HOURS`) — `modules.intelligence`
does not import `modules.ingestion`, so this is a deliberate, small duplication, not an oversight.

Every default here is conservative: ``NEWS_SYNC_ENABLED`` defaults ``False`` — the scheduled task
always fires on Celery Beat's cadence, but does nothing at all until an operator deliberately
opts in (spec §22's DISABLED -> DRY_RUN -> ENABLED sequencing; DRY_RUN is the ``enabled=True`` but
``NEWS_SYNC_MAX_ARTICLES_PER_RUN=0`` case — every step up to the Gemini budget check still runs
and is observable via the run summary, nothing is actually sent to Gemini).
"""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Master switch — the scheduled task no-ops entirely (records a SKIPPED summary, calls no
# provider, no Gemini) while this is False. Never defaults True.
NEWS_SYNC_ENABLED = _env_bool("TITANIQ_NEWS_SYNC_ENABLED", False)

# How often Celery Beat fires the scheduled task (used by beat_schedule.py's timedelta, not by
# the task itself — read here so both the schedule and this module's own docs/tests share one
# source of truth for the default).
NEWS_SYNC_INTERVAL_SECONDS = _env_int("TITANIQ_NEWS_SYNC_INTERVAL_SECONDS", 900)

# A floor on how far back a source's fetch may look, even on a fresh/empty checkpoint — prevents
# a newly-registered source (or a checkpoint reset) from ingesting a feed's entire unbounded
# history on its first scheduled run. 48h comfortably covers this task's own interval with room
# for a missed run or two, without ever behaving like a backfill.
NEWS_SYNC_LOOKBACK_HOURS = _env_int("TITANIQ_NEWS_SYNC_LOOKBACK_HOURS", 48)

# Hard cap on Gemini extraction calls per scheduled run — applied AFTER relevance filtering,
# BEFORE any Gemini call, per spec §6/§12. 20 is deliberately conservative for a v1 default: two
# Gemini calls per article (extract_events + extract_entities), so 40 calls/run at the default
# 15-minute interval is a bounded, predictable ceiling an operator can reason about before
# raising it.
NEWS_SYNC_MAX_ARTICLES_PER_RUN = _env_int("TITANIQ_NEWS_SYNC_MAX_ARTICLES_PER_RUN", 20)

# How far into the future to look for fixtures whose teams/players build the relevance-filter
# vocabulary. 7 days matches the "prediction-window-relevant" framing the spec's own examples use
# (Arsenal vs Chelsea "ahead of... clash") without pulling in every fixture in a season.
NEWS_SYNC_FIXTURE_WINDOW_HOURS = _env_int("TITANIQ_NEWS_SYNC_FIXTURE_WINDOW_HOURS", 168)
