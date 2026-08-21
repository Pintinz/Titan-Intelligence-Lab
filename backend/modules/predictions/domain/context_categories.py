"""Gemini Prediction Reasoning Engine — which contextual evidence categories genuinely exist for
each sport, in TitanIQ's own real data. Deliberately conservative: a category only appears here
if a real repository already exists to fetch it (see `LiveEvidenceGatherer`) — never included
"because a real sport would have it." `sport_code` stays a plain string, matching
`MarketDefinition.sport_code`'s own convention (ADR-008: no enum coupling across module
boundaries) rather than importing `modules.sports.domain.value_objects.SportCode` into this
module's domain layer.

Football gets the full five categories TitanIQ actually ingests (news, injuries, transfers,
suspensions*, lineups). Basketball and baseball share the generic sports-provider injury/lineup
repos but have no dedicated transfer/pitcher/bullpen/rotation repository — claiming those
categories would fabricate a completeness the platform doesn't have. Table tennis has only
player-availability-shaped data (no team-scoped injury/lineup repo applies to an individual
sport). `*` suspensions have no dedicated repository either (confirmed: no
`SuspensionRepositoryPort` exists anywhere in the codebase today) — omitted here for the same
honesty reason, not an oversight.
"""

from __future__ import annotations

SPORT_CONTEXT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "football": ("news", "injuries", "transfers", "lineups"),
    "basketball": ("news", "injuries"),
    "baseball": ("news", "injuries", "lineups"),
    "table_tennis": ("news",),
}


def context_categories_for(sport_code: str) -> tuple[str, ...]:
    """Never raises on an unregistered sport — an honest empty tuple (no categories claimed)
    rather than a `KeyError` that would take down evidence gathering for a sport this mapping
    hasn't been extended to yet."""
    return SPORT_CONTEXT_CATEGORIES.get(sport_code, ())
