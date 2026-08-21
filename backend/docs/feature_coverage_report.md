# TitanIQ Predictive Signal Recovery — Feature Coverage Diagnostic (Phase 2)

Generated 2026-08-17T19:36:38.388152+00:00. 54 markets audited across 4 sports.

Families confirmed (via source-code review, not DB data) to have **zero** feature-
producing calculator anywhere in the codebase: injuries, suspensions.

## baseball

| Family | Markets requiring it | Avg missing_rate | Verdict |
|---|---|---|---|
| odds | 1 | 100.0% | DECLARED_BUT_NEVER_WRITTEN |
| team_form | 11 | 76.9% | WIRED_BUT_UNPOPULATED |
| injuries | 0 | n/a | NO_CALCULATOR |
| suspensions | 0 | n/a | NO_CALCULATOR |

## basketball

| Family | Markets requiring it | Avg missing_rate | Verdict |
|---|---|---|---|
| odds | 1 | 100.0% | DECLARED_BUT_NEVER_WRITTEN |
| team_form | 18 | 60.0% | WIRED_BUT_UNPOPULATED |
| injuries | 0 | n/a | NO_CALCULATOR |
| suspensions | 0 | n/a | NO_CALCULATOR |

## football

| Family | Markets requiring it | Avg missing_rate | Verdict |
|---|---|---|---|
| cards | 6 | n/a (no dataset yet) | WIRED_BUT_UNPOPULATED |
| corners | 6 | n/a (no dataset yet) | WIRED_BUT_UNPOPULATED |
| expected_goals | 12 | 0.0% | WIRED_AND_POPULATED |
| fouls | 6 | n/a (no dataset yet) | WIRED_BUT_UNPOPULATED |
| lineup_continuity | 18 | 100.0% | WIRED_BUT_UNPOPULATED |
| news_intelligence | 12 | 100.0% | WIRED_BUT_UNPOPULATED |
| odds | 3 | 100.0% | WIRED_BUT_UNPOPULATED |
| possession | 6 | n/a (no dataset yet) | WIRED_BUT_UNPOPULATED |
| shots | 6 | n/a (no dataset yet) | WIRED_BUT_UNPOPULATED |
| team_form | 8 | 100.0% | WIRED_BUT_UNPOPULATED |
| transfer_activity | 18 | 100.0% | WIRED_BUT_UNPOPULATED |
| injuries | 0 | n/a | NO_CALCULATOR |
| suspensions | 0 | n/a | NO_CALCULATOR |

## table_tennis

| Family | Markets requiring it | Avg missing_rate | Verdict |
|---|---|---|---|
| odds | 1 | 100.0% | SPORT_UNSUPPORTED |
| team_form | 6 | 100.0% | SPORT_UNSUPPORTED |
| injuries | 0 | n/a | NO_CALCULATOR |
| suspensions | 0 | n/a | NO_CALCULATOR |

