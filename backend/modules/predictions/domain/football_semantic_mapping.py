"""Phase 3 (Sports-Analyst Explainability, Workstream B) — translates real feature keys from
this codebase's own Feature Registry into football-analyst concepts (Phase 3 command §18).

Deliberately a pure, static lookup — no numeric meaning is altered, only the label a human reads.
Every key below matches a real `feature_key` actually registered in this codebase (form
differential calculators, expected-goals, odds, injuries, transfers, lineups, managers — see
`modules/predictions/application/windowed_feature_engineering_service.py`,
`fixture_expected_goals_calculator.py`, and the football feature-market mappings). An unmapped
key is never silently dropped or mis-described — `describe()` falls back to an honest, readable
title-cased rendering of the raw key rather than fabricating a football concept for something this
module doesn't actually know.
"""

from __future__ import annotations

_CONCEPTS: dict[str, str] = {
    "football.fixture.form_possession_pct_diff_last5": "recent territorial/possession control advantage",
    "football.fixture.form_shots_total_diff_last5": "recent attacking shot-volume advantage",
    "football.fixture.form_shots_on_target_diff_last5": "recent ability to generate attempts that test the goalkeeper",
    "football.fixture.form_corners_diff_last5": "recent attacking pressure / final-third activity",
    "football.fixture.form_goals_diff_last5": "recent scoring production",
    "football.fixture.form_goals_conceded_diff_last5": "recent defensive vulnerability",
    "football.fixture.form_fouls_diff_last5": "recent physical/disciplinary intensity",
    "football.fixture.form_cards_yellow_diff_last5": "recent disciplinary pattern",
    "football.fixture.expected_home_goals": "modeled home scoring rate",
    "football.fixture.expected_away_goals": "modeled away scoring rate",
    # Real keys per `market_seeding.py`'s catalog — "market expectation" phrasing deliberately,
    # never "TitanIQ's prediction": this is bookmaker-derived evidence the model weighs alongside
    # its own form/attacking signals, not a claim TitanIQ is making itself (professional-analyst
    # upgrade §12 — a market signal must read as external evidence, not as the platform's own view).
    "football.market.implied_probability_home": "market expectation for the home side",
    "football.market.implied_probability_away": "market expectation for the away side",
    "football.market.overround": "bookmaker margin across the market",
    "football.fixture.injured_players_count": "squad availability burden",
    "football.fixture.key_players_unavailable": "absence of important contributors",
    "football.fixture.lineup_continuity": "starting-XI continuity",
    "football.fixture.transfer_activity": "recent squad turnover",
    "football.fixture.manager_tenure_days": "tactical continuity under the current manager",
    "football.fixture.manager_change_recent": "recent managerial instability/change",
    "football.fixture.news_market_impact": "market-relevant news signal",
}

_SIDE_LABELS = {"home": "home side", "away": "away side"}


def describe(feature_key: str) -> str:
    """Real, known feature -> football-analyst phrase. Unknown feature -> an honest, readable
    fallback (never a fabricated football concept for something this module doesn't recognize)."""
    if feature_key in _CONCEPTS:
        return _CONCEPTS[feature_key]
    tail = feature_key.rsplit(".", 1)[-1]
    return tail.replace("_", " ")


def team_for_feature(feature_key: str) -> str | None:
    """Best-effort side attribution from the key's own naming (e.g. `..._home_...`), never
    guessed beyond what the key itself states. `None` when the feature is side-neutral (most
    "_diff_" features already encode home-minus-away and have no single team to attribute to)."""
    tail = feature_key.lower().rsplit(".", 1)[-1]
    for token, label in _SIDE_LABELS.items():
        if f"_{token}_" in tail or tail.endswith(f"_{token}") or tail.startswith(f"{token}_"):
            return label
    return None


# Phase 3 §19 — which statistical concepts matter for each market family, so a downstream
# explanation layer can select a relevant subset rather than dumping every feature. Real market
# keys only — matches modules/predictions/football/market_seeding.py's actual catalog.
MARKET_FOCUS_CONCEPTS: dict[str, tuple[str, ...]] = {
    "football.match_winner": (
        "form_goals_diff_last5", "form_goals_conceded_diff_last5", "form_shots_on_target_diff_last5",
        "expected_home_goals", "expected_away_goals", "form_possession_pct_diff_last5",
    ),
    "football.first_half_winner": (
        "form_shots_on_target_diff_last5", "form_shots_total_diff_last5", "form_goals_diff_last5",
    ),
    "football.second_half_winner": (
        "form_goals_diff_last5", "form_goals_conceded_diff_last5",
    ),
    "football.first_half_goals": (
        "form_shots_total_diff_last5", "form_shots_on_target_diff_last5", "expected_home_goals", "expected_away_goals",
    ),
    "football.first_half_both_teams_to_score": (
        "form_shots_total_diff_last5", "form_shots_on_target_diff_last5", "form_corners_diff_last5",
    ),
    "football.both_teams_to_score": (
        "form_goals_diff_last5", "form_goals_conceded_diff_last5", "expected_home_goals", "expected_away_goals",
    ),
    "football.total_goals_over_under": (
        "expected_home_goals", "expected_away_goals", "form_shots_total_diff_last5",
    ),
    "football.correct_score": (
        "expected_home_goals", "expected_away_goals",
    ),
}
