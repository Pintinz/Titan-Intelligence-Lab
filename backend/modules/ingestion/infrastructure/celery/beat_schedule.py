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


# Static baseline schedule — args are illustrative (a real deployment's Admin Center would drive
# the actual competition/season list, docs/admin_center.md); the interval *values* are what this
# milestone commits to.
BEAT_SCHEDULE = {
    "sync-countries-football": {
        "task": "ingestion.sync_countries", "schedule": timedelta(seconds=HISTORICAL_IMPORT_INTERVAL_SECONDS * 4),
    },
    "sync-standings-football-epl": {
        "task": "ingestion.sync_standings", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
    },
    "sync-live-fixtures-football-epl": {
        "task": "ingestion.sync_live_fixtures", "schedule": timedelta(seconds=LIVE_FIXTURES_INTERVAL_SECONDS),
    },
    # football-data.org fixture-schedule path (opt-in per competition via
    # CompetitionFixtureSourcePreference) — same "args are illustrative" caveat as every other
    # competition/season-scoped entry above: a real deployment's Admin Center drives the actual
    # competition/season list. PROVIDER_POLL_INTERVAL_SECONDS respects the free tier's 10 req/min
    # cap comfortably for both a schedule check and a results check.
    "sync-upcoming-fixtures-football-data-org": {
        "task": "ingestion.sync_upcoming_fixtures", "schedule": timedelta(seconds=PROVIDER_POLL_INTERVAL_SECONDS),
    },
    "sync-completed-fixtures-football-data-org": {
        "task": "ingestion.sync_completed_fixtures", "schedule": timedelta(seconds=PROVIDER_POLL_INTERVAL_SECONDS),
    },
    "sync-standings-football-data-org": {
        "task": "ingestion.sync_standings_alt", "schedule": timedelta(seconds=STANDINGS_INTERVAL_SECONDS),
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
}
