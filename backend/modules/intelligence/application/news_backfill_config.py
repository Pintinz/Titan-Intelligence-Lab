"""Milestone 12 — News Backfill configuration. Same local `_env_bool`/`_env_int` helper posture
as `news_sync_config.py` (Milestone 10) — small, deliberate per-module duplication rather than a
shared settings module, consistent with every other config constant in this codebase.

``NEWS_BACKFILL_ENABLED`` defaults ``False`` (spec §14): the entry point exists and is fully
testable, but a real (non-dry-run) backfill against a real provider is refused unless an operator
deliberately opts in — mirrors ``NEWS_SYNC_ENABLED``'s exact posture from Milestone 10. Dry-run
requests are never gated by this flag (spec §5: dry-run is "the primary verification mode" and
must always be available to validate a request/inspect what a real run would do).
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


# Master switch for a REAL (non-dry-run) backfill run — never gates dry-run/validation. Never
# defaults True; a real backfill also requires this milestone's separate, explicit live-execution
# approval regardless of this flag's value.
NEWS_BACKFILL_ENABLED = _env_bool("TITANIQ_NEWS_BACKFILL_ENABLED", False)

# Hard upper bound on a single backfill request's window, independent of what the caller asks
# for — spec §4's "apply a hard upper bound to the requested range." A caller requesting a wider
# window than this has its `since` clamped forward (never silently ignored — surfaced on the
# returned plan/summary as `window_clamped`).
NEWS_BACKFILL_MAX_LOOKBACK_DAYS = _env_int("TITANIQ_NEWS_BACKFILL_MAX_LOOKBACK_DAYS", 90)

# Hard cap on Gemini extraction calls per backfill request, applied AFTER relevance filtering,
# BEFORE any Gemini call — identical position in the pipeline to `NEWS_SYNC_MAX_ARTICLES_PER_RUN`
# (Milestone 10 §6/§12). A caller-requested `max_articles` above this is clamped down, never up.
NEWS_BACKFILL_MAX_ARTICLES_PER_RUN = _env_int("TITANIQ_NEWS_BACKFILL_MAX_ARTICLES_PER_RUN", 20)

# Same relevance-vocabulary lookahead window Milestone 10 uses for scheduled sync (fixtures
# scheduled within this many hours of "now" contribute team/player names) — reused as-is rather
# than inventing a second window concept; a historical article is still only worth a Gemini call
# if it can be tied to a currently-relevant team/player/fixture.
NEWS_BACKFILL_FIXTURE_WINDOW_HOURS = _env_int("TITANIQ_NEWS_BACKFILL_FIXTURE_WINDOW_HOURS", 168)
