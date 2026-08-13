"""Celery Beat schedule (docs/roadmap.md Milestone 5 "Scheduler: Historical Import, Live
Synchronization, Standings Updates, Statistics Updates, Feature Refresh, Health Checks,
Provider Polling, Adaptive Scheduling, Quota-Aware Scheduling").

``compute_adaptive_interval`` is a pure function, not a custom ``celery.beat.Scheduler``
subclass — Beat's schedule is otherwise evaluated ahead of time, and building a scheduler that
re-consults live quota state on every tick is a real (and separable) piece of work belonging to
a later pass, not this milestone's foundation. What Milestone 5 delivers: the *policy* — given
remaining quota, how much longer should the interval be — as a tested, reusable function, wired
into the static schedule below at startup. Runtime re-evaluation against live
``QuotaIntelligenceEngine`` state is a documented follow-up, not implemented here.
"""

from __future__ import annotations

from datetime import timedelta

# Baselines an operator would tune per provider/competition in the Admin Center once it exists
# (docs/admin_center.md — Feature Flags/Configuration Management, Milestone 15).
HISTORICAL_IMPORT_INTERVAL_SECONDS = 6 * 3600
STANDINGS_INTERVAL_SECONDS = 3600
STATISTICS_INTERVAL_SECONDS = 1800
LIVE_FIXTURES_INTERVAL_SECONDS = 30
PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = 300
PROVIDER_POLL_INTERVAL_SECONDS = 900
# Retraining is a heavy, dataset-build-plus-multi-algorithm-training operation — a 6-hour cadence
# (matching HISTORICAL_IMPORT_INTERVAL_SECONDS's order of magnitude) is enough to catch drift or
# staleness promptly without hammering the training pipeline for markets that rarely need it.
SCHEDULED_RETRAINING_CHECK_INTERVAL_SECONDS = 6 * 3600
# Calibration fitting is cheap (reads outcome history, fits a small logistic regression) compared
# to retraining — an hourly cadence (matching STANDINGS_INTERVAL_SECONDS) keeps calibrated
# confidence tracking newly-completed fixtures promptly without the training-pipeline cost.
SCHEDULED_CALIBRATION_CHECK_INTERVAL_SECONDS = 3600
# Milestone 5 (Verified Pre-Match Data Availability) — matches PROVIDER_POLL_INTERVAL_SECONDS's
# free-tier-safe cadence (same 10 req/min budget every other football-data.org-class entry
# respects). At 15 minutes, a fixture's LINEUP_PREMATCH_WINDOW_MINUTES (default 90) is checked
# roughly 6 times before it closes — several real chances to catch official lineups once the
# provider actually publishes them, without polling aggressively enough to burn quota on fixtures
# that are still hours from kickoff. Injuries/transfers ride the same schedule (Milestone 5 §1
# scopes them to "fixtures within the relevant prediction window," not a separate cadence) —
# splitting them onto their own interval would add a second config knob for no real behavioral
# gain, since `sync_upcoming_structured_intelligence` already dedupes team-level syncs per run.
STRUCTURED_INTEL_INTERVAL_SECONDS = 900
# Milestone 10 — the scheduled news sync task's own interval, matching
# `modules.intelligence.application.news_sync_config.NEWS_SYNC_INTERVAL_SECONDS`'s default (900s).
# Defined locally rather than imported, same posture this file already takes for
# SCHEDULED_RETRAINING_CHECK_INTERVAL_SECONDS/SCHEDULED_CALIBRATION_CHECK_INTERVAL_SECONDS below
# (both predictions-owned tasks, neither constant imported from modules.predictions either) — this
# module is the one place every Beat interval lives, regardless of which module's task it drives.
NEWS_SYNC_SCHEDULE_INTERVAL_SECONDS = 900


def compute_adaptive_interval(base_interval_seconds: int, quota_remaining_pct: float) -> int:
    """Lengthens a sync interval as a provider's remaining quota shrinks — "Quota-Aware
    Scheduling." At >=50% remaining: unchanged. 20-50%: doubled. <20%: quadrupled. Below 5%
    remaining, eight times the base interval — deliberately conservative rather than stopping
    entirely, since a still-running (if infrequent) sync beats silently going stale.
    """
    if quota_remaining_pct < 0 or quota_remaining_pct > 100:
        raise ValueError(f"quota_remaining_pct must be within [0, 100], got {quota_remaining_pct}")
    if quota_remaining_pct >= 50:
        multiplier = 1
    elif quota_remaining_pct >= 20:
        multiplier = 2
    elif quota_remaining_pct >= 5:
        multiplier = 4
    else:
        multiplier = 8
    return base_interval_seconds * multiplier


# Audit fix (2026-08-10): every entry below now carries a real `args` tuple. Previously none did
# — every `ingestion.sync_*` task requires `sport_code`/`competition_ref`/`season_label`/
# `season_id` as required positional arguments with no defaults, so if Beat had ever actually
# fired one of these entries it would have failed with a missing-arguments TypeError. `now_iso`
# is deliberately the one arg still omitted here — it's now optional on every task (see
# `_resolve_now` in tasks.py) and resolves to the real time of each firing, since a value baked
# into this module-level dict at worker startup would go stale after the very first run.
# competition_ref values are each provider's real external league ID (verified live against
# api-sports.io, not guessed); season labels are pinned to a season within the free-tier's
# 2022-2024 access window (docs note this restriction repo-wide, e.g. `scripts/seed_football_markets.py`).
BEAT_SCHEDULE = {
    "sync-countries-football": {
        "task": "ingestion.sync_countries", "schedule": timedelta(seconds=HISTORICAL_IMPORT_INTERVAL_SECONDS * 4),
        "args": ("football",),
    },
    "sync-standings-football-epl": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("football", "39", "2023", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    "sync-live-fixtures-football-epl": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
        "args": ("football", "39", "2023", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    "sync-countries-basketball": {
        "task": "ingestion.sync_countries", "schedule": timedelta(seconds=HISTORICAL_IMPORT_INTERVAL_SECONDS * 4),
        "args": ("basketball",),
    },
    "sync-standings-basketball-nba": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("basketball", "12", "2023-2024", "0b1c3ee3-88c9-4f2c-83b3-78144a3481d3"),
    },
    "sync-live-fixtures-basketball-nba": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
        "args": ("basketball", "12", "2023-2024", "0b1c3ee3-88c9-4f2c-83b3-78144a3481d3"),
    },
    "sync-standings-basketball-euroleague": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("basketball", "120", "2023", "0cfa00cc-1fd9-433d-a8d9-cdf7d7cbab6f"),
    },
    "sync-live-fixtures-basketball-euroleague": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
        "args": ("basketball", "120", "2023", "0cfa00cc-1fd9-433d-a8d9-cdf7d7cbab6f"),
    },
    "sync-countries-baseball": {
        "task": "ingestion.sync_countries", "schedule": timedelta(seconds=HISTORICAL_IMPORT_INTERVAL_SECONDS * 4),
        "args": ("baseball",),
    },
    "sync-standings-baseball-mlb": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("baseball", "1", "2023", "0c67a838-9049-4bab-b3e4-6bbf675fc96b"),
    },
    "sync-live-fixtures-baseball-mlb": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
        "args": ("baseball", "1", "2023", "0c67a838-9049-4bab-b3e4-6bbf675fc96b"),
    },
    "sync-standings-baseball-npb": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("baseball", "2", "2023", "0ee2290f-e216-48a1-bb2f-f92ec4f39d51"),
    },
    "sync-live-fixtures-baseball-npb": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
        "args": ("baseball", "2", "2023", "0ee2290f-e216-48a1-bb2f-f92ec4f39d51"),
    },
    # football-data.org fixture-schedule path (opt-in per competition via
    # CompetitionFixtureSourcePreference) — competition_id/season_label/season_id below are EPL's
    # real values, matching the real CompetitionFixtureSourcePreference row already configured for
    # it (provider_competition_ref "PL"). PROVIDER_POLL_INTERVAL_SECONDS respects the free tier's
    # 10 req/min cap comfortably for both a schedule check and a results check.
    "sync-upcoming-fixtures-football-data-org": {
        "task": "ingestion.sync_upcoming_fixtures", "schedule": timedelta(seconds=PROVIDER_POLL_INTERVAL_SECONDS),
        "args": ("football", "a2721390-8d51-4011-905b-d6379e425675", "2023", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    "sync-completed-fixtures-football-data-org": {
        "task": "ingestion.sync_completed_fixtures", "schedule": timedelta(seconds=PROVIDER_POLL_INTERVAL_SECONDS),
        "args": ("football", "a2721390-8d51-4011-905b-d6379e425675", "2023", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    "sync-standings-football-data-org": {
        "task": "ingestion.sync_standings_alt", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
        "args": ("football", "a2721390-8d51-4011-905b-d6379e425675", "2023", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    # Milestone 11B — Provider Registry health monitoring (docs/admin_center.md §2a), the follow-
    # up ADR-011 flagged as needing Celery beat rather than a new scheduler.
    "check-all-provider-health": {
        "task": "admin.check_all_provider_health", "schedule": timedelta(seconds=PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS),
    },
    # Audit fix (2026-08-02) — RetrainingScheduler/AutomaticModelSelectionService both already
    # existed but were only reachable via a manual Ops Center button; this is the automatic half.
    "check-scheduled-retraining": {
        "task": "predictions.check_scheduled_retraining",
        "schedule": timedelta(seconds=SCHEDULED_RETRAINING_CHECK_INTERVAL_SECONDS),
    },
    # Audit fix (2026-08-02) — CalibratorPort.fit() had zero real call sites; every "calibrated"
    # probability was actually the unfitted identity transform. This is the missing caller.
    "check-scheduled-calibration": {
        "task": "predictions.check_scheduled_calibration",
        "schedule": timedelta(seconds=SCHEDULED_CALIBRATION_CHECK_INTERVAL_SECONDS),
    },
    # Milestone 5 — the only real caller of `SyncOrchestrator.sync_upcoming_structured_intelligence`,
    # and therefore the only path that can ever produce `SyncTrigger.LIVE_SCHEDULED` (see that
    # task's own docstring). Football/EPL only: injuries/transfers/lineups reconciliation exists
    # today only for football (docs/milestone3_historical_data_audit.md), matching every other
    # sport-scoped entry above. season_id is EPL's real, already-configured value (same one
    # "sync-standings-football-epl"/"sync-live-fixtures-football-epl" already use).
    "sync-upcoming-structured-intelligence-football-epl": {
        "task": "ingestion.sync_upcoming_structured_intelligence",
        "schedule": timedelta(seconds=STRUCTURED_INTEL_INTERVAL_SECONDS),
        "args": ("football", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
    # Milestone 10 — the scheduled news sync entry point. Always registered (Beat's schedule is
    # evaluated once at worker startup, so a runtime env-var toggle can't be expressed by
    # conditionally omitting this dict entry) — the task itself checks
    # `news_sync_config.NEWS_SYNC_ENABLED` first and no-ops (no provider call, no Gemini call)
    # whenever it's False, which it always defaults to. Same EPL season_id every other football
    # entry above already uses. `NEWS_SYNC_INTERVAL_SECONDS` (default 900s) is intelligence's own
    # config constant, not one of the ingestion-module intervals above — read here only for the
    # schedule's own interval value, matching this module's already-established local-duplication
    # posture for anything intelligence-owned.
    "sync-scheduled-news-football-epl": {
        "task": "intelligence.sync_scheduled_news",
        "schedule": timedelta(seconds=NEWS_SYNC_SCHEDULE_INTERVAL_SECONDS),
        "args": ("football", "21521495-4dd4-4c50-a41d-d88642322804"),
    },
}
