"""Pluggable per-market outcome resolver contract (Milestone 9.2 — Market Registry &
Prediction Domain Normalization). Formalizes the shape every market's real-outcome-from-final-
score function should have, so a market's resolver can be looked up and invoked generically —
"Never hardcode large if/else chains."

This is the Phase 1 (architecture) half of the contract; wiring it into prediction generation and
evaluation is deliberately out of scope for this phase (see
`modules.predictions.domain.market_outcome_registry`'s module docstring). The concrete resolver
callables `modules.predictions.application.outcome_resolution_service.MARKET_OUTCOME_RESOLVERS`
already registers structurally satisfy this same "given a final score, return a resolved label or
None" shape — that module is untouched here, not superseded.
"""

from __future__ import annotations

from typing import Protocol


class MarketOutcomeResolverPort(Protocol):
    """Resolves a market's real-world outcome label from a fixture's final score. Returns
    ``None`` when the outcome genuinely cannot be determined from a final score alone (e.g. the
    match ended in a state this market's resolver doesn't model, or required data — a line, a
    segment score, a player stat — isn't available) — implementations must never fabricate a
    label rather than return ``None``."""

    def resolve(self, home_score: int, away_score: int) -> str | None: ...
