"""Maps a `MarketKind` to the `PredictorPort` implementation that serves it — the lookup
`PredictionEngine` (Part 4, "Prediction Model" pipeline stage) uses so it never has to know
which concrete predictor class backs a given market, only its `MarketKind`.

Composition wiring (each app's composition module) registers the real
`WeightedLogisticPredictor`/`WeightedLinearPredictor` instances against every `MarketKind` they
support — a future trained-model adapter registers itself here too, without this registry or
`PredictionEngine` changing (docs/decisions.md ADR-008 adapter-swap posture).

**Milestone 9.1 addition (docs/decisions.md ADR-050):** the `MarketKind`-only lookup above was
sufficient while every predictor was a market-kind-generic formula (`WeightedLogisticPredictor`
carries no market-specific fitted state — `FeatureMarketMapping.weight` supplies all the
per-market specificity it needs). A trained ML model can't work that way: a LightGBM champion
fitted for `football.match_result` has different tree splits than one fitted for
`basketball.match_winner`, even though both markets share `MarketKind.BINARY`. `register_for_market`/
the ``market_key`` parameter on `get()` let composition wiring register a specific trained
predictor for one named market; `get()` checks that mapping first and only falls back to the
`MarketKind`-level default (today, always a weighted predictor) if nothing is registered for the
market. Purely additive — every existing `get(market_kind)` call site and test keeps working
unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modules.predictions.domain.value_objects import MarketKind
from modules.predictions.ports.predictor import PredictorPort


class NoPredictorRegisteredError(KeyError):
    pass


@dataclass
class PredictorRegistry:
    _predictors: dict[MarketKind, PredictorPort] = field(default_factory=dict)
    _market_predictors: dict[str, PredictorPort] = field(default_factory=dict)

    def register(self, market_kind: MarketKind, predictor: PredictorPort) -> None:
        self._predictors[market_kind] = predictor

    def register_many(self, market_kinds: tuple[MarketKind, ...], predictor: PredictorPort) -> None:
        for kind in market_kinds:
            self.register(kind, predictor)

    def register_for_market(self, market_key: str, predictor: PredictorPort) -> None:
        """Registers ``predictor`` for exactly one named market — takes precedence over the
        `MarketKind`-level default in `get()`. Used to serve a market's specific trained ML
        champion once one exists (Milestone 9.1); unregistering (e.g. on rollback to the
        weighted fallback) is done by calling this again with the fallback predictor."""
        self._market_predictors[market_key] = predictor

    def get(self, market_kind: MarketKind, market_key: str | None = None) -> PredictorPort:
        if market_key is not None:
            market_predictor = self._market_predictors.get(market_key)
            if market_predictor is not None:
                return market_predictor

        predictor = self._predictors.get(market_kind)
        if predictor is None:
            raise NoPredictorRegisteredError(f"no predictor registered for market_kind '{market_kind.value}'")
        return predictor
