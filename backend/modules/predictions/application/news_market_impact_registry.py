"""Milestone 9 — Market Impact Registry (spec §11): "Do NOT calculate one generic impact score
and apply it to every market... Each rule must define: event_type, entity_type, entity_role,
market, direction, magnitude, confidence weighting, TTL, feature name, explanation template."

Deliberately a representative rule set, not exhaustive — the same ADR-narrowing posture every
other v1 component in this codebase takes (Milestone 6's "one representative windowed feature",
Milestone 7's transfer-activity scope). Covers the two roles with the clearest, most defensible
real football signal (forward/striker and goalkeeper absences) across three market-specific
feature dimensions, rather than one blanket composite: goal output, clean-sheet likelihood, and
BTTS — a forward's absence and a goalkeeper's absence affect these three very differently, which
is exactly the "market-specific, not generic" requirement this registry exists to satisfy.
Extending to more roles/markets is additive — no existing rule changes shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from modules.intelligence.application.news_validity_policy import validity_window_hours
from modules.intelligence.domain.value_objects import NewsEventType

# Player.position (API-Football's own lowercase provider vocabulary, confirmed live against
# dev.db) -> the role vocabulary this registry's rules key on. "attacker"/"forward" both
# normalize to FORWARD — a provider label difference, not a distinct real role.
PLAYER_ROLE_BY_POSITION: dict[str, str] = {
    "goalkeeper": "goalkeeper",
    "defender": "defender",
    "midfielder": "midfielder",
    "attacker": "forward",
    "forward": "forward",
}


def normalize_player_role(position: str | None) -> str | None:
    if position is None:
        return None
    return PLAYER_ROLE_BY_POSITION.get(position.lower())


@dataclass(frozen=True)
class MarketImpactRule:
    event_type: NewsEventType
    entity_role: str | None  # None = applies regardless of role (not used by any rule below yet)
    market_key: str
    direction: float  # +1.0 (raises the market's probability) or -1.0 (lowers it)
    magnitude: float  # base weight before confidence-tier adjustment (CONFIDENCE_WEIGHT_MULTIPLIERS)
    ttl_hours: int
    feature_key_stem: str  # combined with "home_"/"away_" at write time, matching M6/M7's convention
    explanation_template: str  # {player}/{team}/{market} placeholders, filled by the impact engine


def _rule(
    event_type: NewsEventType, entity_role: str, market_key: str, direction: float, magnitude: float,
    feature_key_stem: str, explanation_template: str,
) -> MarketImpactRule:
    return MarketImpactRule(
        event_type=event_type, entity_role=entity_role, market_key=market_key, direction=direction,
        magnitude=magnitude, ttl_hours=validity_window_hours(event_type), feature_key_stem=feature_key_stem,
        explanation_template=explanation_template,
    )


MARKET_IMPACT_RULES: tuple[MarketImpactRule, ...] = (
    # -- Forward/striker: own team's goal output -------------------------------------------
    _rule(
        NewsEventType.INJURY, "forward", "football.total_goals_over_under", -1.0, 0.4,
        "news.football.goal_impact", "{player} ({role}) injury reduces {team}'s expected goal output",
    ),
    _rule(
        NewsEventType.SUSPENSION, "forward", "football.total_goals_over_under", -1.0, 0.4,
        "news.football.goal_impact", "{player} ({role}) suspension reduces {team}'s expected goal output",
    ),
    _rule(
        NewsEventType.RECOVERY, "forward", "football.total_goals_over_under", 1.0, 0.3,
        "news.football.goal_impact", "{player} ({role}) returning from injury restores {team}'s attacking output",
    ),
    # -- Forward/striker: own team's BTTS likelihood (a weaker attack scores less often) ----
    _rule(
        NewsEventType.INJURY, "forward", "football.both_teams_to_score", -1.0, 0.3,
        "news.football.btts_impact", "{player} ({role}) injury reduces {team}'s likelihood of scoring",
    ),
    # -- Goalkeeper: own team's clean-sheet likelihood --------------------------------------
    _rule(
        NewsEventType.INJURY, "goalkeeper", "football.home_clean_sheet", -1.0, 0.4,
        "news.football.clean_sheet_impact", "{player} ({role}) injury reduces {team}'s clean-sheet likelihood",
    ),
    _rule(
        NewsEventType.SUSPENSION, "goalkeeper", "football.home_clean_sheet", -1.0, 0.4,
        "news.football.clean_sheet_impact", "{player} ({role}) suspension reduces {team}'s clean-sheet likelihood",
    ),
    _rule(
        NewsEventType.RECOVERY, "goalkeeper", "football.home_clean_sheet", 1.0, 0.3,
        "news.football.clean_sheet_impact", "{player} ({role}) returning from injury restores {team}'s defensive solidity",
    ),
    # -- Goalkeeper: own team's BTTS likelihood (a weaker defense concedes more often) ------
    _rule(
        NewsEventType.INJURY, "goalkeeper", "football.both_teams_to_score", 1.0, 0.3,
        "news.football.btts_impact", "{player} ({role}) injury increases the likelihood {team} concedes",
    ),
)

# `market_key` above uses `football.home_clean_sheet` as the *canonical* representative of the
# clean-sheet market pair purely to declare one row per rule — `NewsMarketImpactEngine` maps every
# rule's `feature_key_stem` to BOTH the home and away variant of any market whose key contains
# "clean_sheet" (home_clean_sheet/away_clean_sheet) or is otherwise side-symmetric, since a
# feature computed for "this team, whichever side it plays" is equally relevant to either side's
# specific market — see `news_market_impact_engine.py`'s `_TARGET_MARKETS_BY_FEATURE_STEM`.
CLEAN_SHEET_MARKET_PAIR: tuple[str, str] = ("football.home_clean_sheet", "football.away_clean_sheet")
GOAL_OUTPUT_MARKETS: tuple[str, ...] = (
    "football.total_goals_over_under", "football.home_team_total_goals", "football.away_team_total_goals",
)
BTTS_MARKETS: tuple[str, ...] = ("football.both_teams_to_score",)
