# Milestone 20 — Blocked Training Report

Per §12 of the Milestone 20 master command: `TrainingPreflightService` reports **0 of 38 markets
READY** for Challenger training, after the one legitimately available fix (durable Dataset
persistence, §17 of `docs/milestone20_verification_report.md`) was implemented. No model was
trained. No Champion was modified. This report documents why, per market bucket, and what would
need to change for a future attempt to succeed.

**M20 = BLOCKED BY READINESS. This is an acceptable final outcome (§12, §26 STATE C).**

---

## All Failed Markets and Exact Blockers

### Bucket A — 14 genuinely-trained football markets

`correct_score`, `total_goals_over_under` (+4 threshold variants), `home_win_to_nil`,
`home_team_total_goals`, `home_clean_sheet`, `away_win_to_nil`, `away_team_total_goals`,
`away_clean_sheet`, `match_winner`, `both_teams_to_score`.

Every one fails identically on 3 checks (re-verified live against `dev.db` after implementation,
matching `docs/milestone19_preimplementation_audit.md` and
`docs/milestone20_preimplementation_audit.md` exactly):

- `training_inference_feature_parity` — the 4-6 gated intelligence features (`home/away_lineup_continuity`,
  `home/away_transfer_activity`, and for 9 of the 14, two `news.*` impact features) required at
  live inference have never appeared in a single historical training sample.
- `required_feature_coverage_acceptable` — 0.0% coverage for every one of those same features.
- `dataset_provenance_persisted` — no `Dataset` has ever been durably registered for these markets
  (the repository can now persist one, per this milestone's fix, but none has been registered,
  since no training run was performed).

### Bucket B — 5 heuristic-placeholder football markets + `football.match_result` (deprecated)

`first_half_both_teams_to_score`, `first_half_goals`, `first_half_winner`, `second_half_winner`,
`match_result`. Zero `prediction_outcomes` ever recorded — `DatasetBuilder.build()` returns an
empty sample set. Fails on `sufficient_labeled_observations`, `temporal_reference_present`,
`temporal_split_valid`, and `dataset_provenance_persisted`. Notably these 5 have **no gated
intelligence requirement at all** — a future ordinary match-outcome backfill (no lineup/transfer/
news data needed) could in principle unblock one of these without touching provenance-sensitive
architecture. Out of scope for this milestone.

### Bucket C — 24 basketball/baseball/table_tennis markets

Zero fixtures have ever produced a `Prediction`/`PredictionOutcome` for any non-football sport
(confirmed unchanged since Milestone 17). Same 4 failing checks as Bucket B. Unrelated to
Milestone 20's mandate; requires provider/feature-calculator work outside this milestone's scope
(tracked separately, tasks #158/#159).

---

## Why Each Blocker Exists

**Bucket A (the genuine, structural blocker):** `VERIFIED_PRE_MATCH` provenance for
lineup/transfer/news data can only be produced by the `LIVE_SCHEDULED` Celery Beat sync running
*before* a fixture's kickoff. Every one of the 14 markets' ~652–824 historical observations comes
from fixtures that had already completed before this platform's live sync infrastructure
(Milestones 5/10) ever ran against them. That window is permanently closed for those specific
fixtures — no code change can retroactively produce a legitimate pre-match observation for a match
that already happened. `intelligence_sync_runs` confirms zero `LIVE_SCHEDULED` runs have ever
executed in this `dev.db` (23 runs, all `trigger='manual'`).

**Buckets B/C:** simple absence of any historical prediction/outcome data — a data-volume gap, not
a provenance gap, and not required-feature-related at all for Bucket B specifically.

## What Was Safely Fixed This Milestone

`dataset_provenance_persisted` — implemented `SqlAlchemyDatasetRepository` (mapper + repository +
composition wiring), closing the one legitimately-resolvable gap identified in Phase 0. This does
**not** change the READY=0 outcome for any market today (Bucket A's parity failures dominate
independently; Buckets B/C have no dataset to persist in the first place), but removes a
structural blocker that will matter the moment real training data exists. See
`docs/milestone20_verification_report.md` §17 for full implementation detail.

## What Remains Impossible Without New Data

All of Bucket A's parity/coverage failures, for the *existing* historical fixture set,
permanently. The only legitimate path forward is real calendar time passing with
`NEWS_SYNC_ENABLED=true` and the structured-intelligence Celery Beat schedule genuinely running
against genuinely-upcoming fixtures, accumulating an entirely new set of `VERIFIED_PRE_MATCH`
observations going forward. That is an operational/data-accumulation decision outside a single
coding session's authority — explicitly not attempted here, per Milestone 20 §1's prohibition on
fabricating provenance or backdating availability timestamps.

## Recommended Future Work

1. **Operational**: enable `NEWS_SYNC_ENABLED` and the structured-intelligence sync for real
   upcoming fixtures, and let it run for an extended period (weeks/months, scaled to fixture
   volume) to accumulate genuine `VERIFIED_PRE_MATCH` lineup/transfer/news observations. Re-run
   `python scripts/run_training_preflight.py --all-trained-football` periodically — the moment any
   market's gated-feature coverage rises above the `required_feature_coverage_acceptable`
   threshold, `TrainingPreflightService` will report it, mechanically, no manual re-audit needed.
2. **Bucket B**: consider a plain match-outcome backfill (no gated intelligence involved) for one
   of the 5 heuristic markets, most likely `first_half_winner` or `second_half_winner`, as a much
   shorter path to a second READY-capable market family.
3. **Per-sample feature-version provenance** (Milestone 19 audit §12) — still latent, not blocking
   today, worth closing before any market does become training-ready.
4. **Community Intelligence** — deferred, out of scope (see
   `docs/milestone20_verification_report.md` §26).

This is the honest, evidence-based conclusion of Project TitanIQ's Milestone 20 — and, per the
master command, the final milestone.
