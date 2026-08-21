from __future__ import annotations

import pytest

from modules.predictions.application.feature_family_taxonomy import (
    NO_CALCULATOR_CONFIRMED_FAMILIES,
    SPORTS_WITH_REAL_ODDS_WRITER,
    classify_feature_key,
)


@pytest.mark.parametrize(
    "feature_key,expected_family",
    [
        ("football.fixture.form_shots_on_target_diff_last5", "team_form"),
        ("football.team.form_shots_on_target_last5", "team_form"),
        ("football.fixture.form_possession_pct_diff_last5", "possession"),
        ("football.fixture.form_shots_total_diff_last5", "shots"),
        ("football.fixture.form_corners_diff_last5", "corners"),
        ("football.fixture.form_fouls_diff_last5", "fouls"),
        ("football.fixture.form_cards_yellow_diff_last5", "cards"),
        ("football.fixture.expected_home_goals", "expected_goals"),
        ("football.fixture.expected_away_goals", "expected_goals"),
        ("football.fixture.home_lineup_continuity", "lineup_continuity"),
        ("football.fixture.away_lineup_continuity", "lineup_continuity"),
        ("football.fixture.home_transfer_activity", "transfer_activity"),
        ("football.fixture.away_transfer_activity", "transfer_activity"),
        ("football.market.implied_probability_home", "odds"),
        ("football.market.implied_probability_away", "odds"),
        ("football.market.overround", "odds"),
        ("news.football.home_goal_impact", "news_intelligence"),
        ("news.football.away_clean_sheet_impact", "news_intelligence"),
        ("news.football.home_btts_impact", "news_intelligence"),
        ("basketball.team.form_points_last5", "team_form"),
        ("basketball.fixture.form_points_diff_last5", "team_form"),
        ("basketball.market.overround", "odds"),
        ("basketball.market.implied_probability_home", "odds"),
        ("baseball.team.form_runs_last5", "team_form"),
        ("baseball.fixture.form_runs_diff_last5", "team_form"),
        ("baseball.market.overround", "odds"),
        ("table_tennis.team.form_points_won_last5", "team_form"),
        ("table_tennis.market.overround", "odds"),
    ],
)
def test_classify_feature_key_known_patterns(feature_key, expected_family):
    assert classify_feature_key(feature_key) == expected_family


@pytest.mark.parametrize(
    "feature_key",
    [
        "football.fixture.unknown_signal",
        "basketball.player.injury_status",
        "",
        "random_key_no_dots",
    ],
)
def test_classify_feature_key_unknown_returns_none(feature_key):
    assert classify_feature_key(feature_key) is None


def test_no_calculator_confirmed_families_are_never_matched_by_any_real_pattern():
    """These families are asserted absent by source-code confirmation, not by classify_feature_key
    ever seeing a real key for them — no pattern in the taxonomy should coincidentally produce
    these family names, or the distinction between 'confirmed absent' and 'not yet observed'
    collapses."""
    from modules.predictions.application.feature_family_taxonomy import FEATURE_KEY_PREFIXES

    matched_families = {family for _, family in FEATURE_KEY_PREFIXES}
    for family in NO_CALCULATOR_CONFIRMED_FAMILIES:
        assert family not in matched_families


def test_only_football_has_a_real_odds_writer():
    assert SPORTS_WITH_REAL_ODDS_WRITER == ("football",)
