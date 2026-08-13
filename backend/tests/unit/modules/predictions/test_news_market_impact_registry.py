from __future__ import annotations

from modules.intelligence.application.news_validity_policy import validity_window_hours
from modules.predictions.application.news_market_impact_registry import (
    MARKET_IMPACT_RULES,
    normalize_player_role,
)


def test_normalize_player_role_maps_attacker_and_forward_to_forward():
    assert normalize_player_role("attacker") == "forward"
    assert normalize_player_role("forward") == "forward"


def test_normalize_player_role_is_case_insensitive():
    assert normalize_player_role("Goalkeeper") == "goalkeeper"


def test_normalize_player_role_returns_none_for_unknown_position():
    assert normalize_player_role("physio") is None
    assert normalize_player_role(None) is None


def test_every_rule_ttl_matches_its_event_types_validity_window():
    """Each rule's `ttl_hours` must come from the real validity policy, never a hand-fabricated
    number that could silently drift out of sync with the documented per-event-type rationale."""
    for rule in MARKET_IMPACT_RULES:
        assert rule.ttl_hours == validity_window_hours(rule.event_type)


def test_every_rule_direction_is_plus_or_minus_one():
    for rule in MARKET_IMPACT_RULES:
        assert rule.direction in (1.0, -1.0)


def test_every_rule_magnitude_is_a_positive_fraction():
    for rule in MARKET_IMPACT_RULES:
        assert 0.0 < rule.magnitude <= 1.0


def test_rules_cover_three_distinct_feature_dimensions_not_one_generic_score():
    """The spec's core requirement: market-specific impact, not one blanket composite."""
    stems = {rule.feature_key_stem for rule in MARKET_IMPACT_RULES}
    assert stems == {
        "news.football.goal_impact", "news.football.clean_sheet_impact", "news.football.btts_impact",
    }


def test_forward_injury_reduces_goal_output_while_goalkeeper_injury_raises_btts_risk():
    """Same INJURY event type, opposite roles, genuinely different market effects — proof the
    registry isn't just replaying one signal under different labels."""
    forward_goal_rule = next(
        r for r in MARKET_IMPACT_RULES
        if r.entity_role == "forward" and r.market_key == "football.total_goals_over_under"
    )
    goalkeeper_btts_rule = next(
        r for r in MARKET_IMPACT_RULES
        if r.entity_role == "goalkeeper" and r.market_key == "football.both_teams_to_score"
    )
    assert forward_goal_rule.direction == -1.0  # weaker attack -> fewer expected goals
    assert goalkeeper_btts_rule.direction == 1.0  # weaker defense -> opponent more likely to score
