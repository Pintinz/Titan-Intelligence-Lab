"""Explainability Engine (Milestone 9 Part 4): assembles the `ExplanationBundle` every
prediction must carry — Top Positive Features, Top Negative Features, Feature Importance,
Knowledge Graph Evidence, News Contribution, Community Contribution, AI Explanation.

Composes rather than re-implements: ranking `PredictorOutput.feature_contributions` into
top-positive/top-negative/importance is this engine's own real work. Knowledge Graph evidence,
News contribution, and Community contribution all come from a single call to Milestone 8's
`IntelligenceRetrievalService.retrieve_all()` (itself composing Milestone 7's Knowledge Graph
retrieval) — one call, three modalities, split by `IntelligenceRetrievalDocument.modality`.
`ai_explanation` comes from Gemini's `TextIntelligenceProviderPort.explain()`, given the already-
ranked feature importances as its context — the LLM narrates, it never decides the ranking
(Milestone 9 Part 1: "Predictions must never originate from an LLM").
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from modules.ingestion.ports.cache import SyncCachePort
from modules.intelligence.application.intelligence_retrieval_service import IntelligenceRetrievalService
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort
from modules.predictions.domain.entities import ExplanationBundle
from modules.predictions.infrastructure.ml.shap_explainer_service import SHAPExplainerService
from modules.predictions.ports.ml_model import PredictionModelPort
from modules.predictions.ports.predictor import PredictorOutput

# Real Gemini quota is scarce (the free tier caps at a handful of requests/day/model — see
# `football_explanation_service.py`'s own note on this) — every sport/market's base narration
# goes through this one engine, so an unprotected re-narration here wastes quota across the whole
# app, not just football. `PredictionCacheService.get_or_generate`'s own 5-minute TTL already
# avoids re-calling this engine for a rapid repeat click on the exact same prediction, but a
# prediction that regenerates after that window — with an identical ranked feature set, because
# nothing about the fixture actually changed — still re-narrates from scratch without this cache.
_CACHE_TTL_SECONDS = 6 * 60 * 60


def _ranking_hash(positive: tuple, negative: tuple, probability: float) -> str:
    """A stable hash of exactly what determines this narration's content — the ranked feature
    contributions Gemini is actually handed, plus the published probability. Two generations with
    an identical ranking (the common case for a fixture nothing new has happened to) share a
    cache entry; any real change to the ranking or probability produces a different key."""
    payload = f"{positive}|{negative}|{round(probability, 4)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass
class ExplainabilityEngine:
    retrieval: IntelligenceRetrievalService
    text_intelligence: TextIntelligenceProviderPort
    top_n: int = 5
    shap_explainer: SHAPExplainerService | None = None  # Milestone 9.1 — None keeps M9 behavior identical
    # `None` (the default) preserves every existing test/caller's exact prior behavior (always
    # narrates fresh); real production wiring (composition.py) provides the same Redis-backed
    # `SyncCachePort` every other Gemini-calling service already uses.
    cache: SyncCachePort | None = None

    async def explain(
        self, subject_ref: str, market_key: str, predictor_output: PredictorOutput, probability: float
    ) -> ExplanationBundle:
        ranked = sorted(predictor_output.feature_contributions.items(), key=lambda kv: kv[1], reverse=True)
        positive = tuple((key, value) for key, value in ranked if value > 0)[: self.top_n]
        negative = tuple(sorted((kv for kv in ranked if kv[1] < 0), key=lambda kv: kv[1]))[: self.top_n]

        total_abs = sum(abs(value) for _, value in ranked)
        feature_importance = (
            {key: abs(value) / total_abs for key, value in ranked} if total_abs > 0 else {key: 0.0 for key, _ in ranked}
        )

        documents = await self.retrieval.retrieve_all(subject_ref)
        knowledge_graph_evidence = tuple(d.text for d in documents if d.modality == "knowledge_graph")
        news_contribution = tuple(d.text for d in documents if d.modality == "news")
        community_contribution = tuple(d.text for d in documents if d.modality == "community")

        cache_key = f"ai_explanation:{subject_ref}:{market_key}:{_ranking_hash(positive, negative, probability)}"
        ai_explanation = None
        if self.cache is not None:
            try:
                ai_explanation = await self.cache.get(cache_key)
            except Exception:  # noqa: BLE001 — a broken cache backend degrades to "always miss," never an error
                ai_explanation = None

        if ai_explanation is None:
            ai_explanation = await self.text_intelligence.explain(
                {
                    "market_key": market_key,
                    "subject_ref": subject_ref,
                    "probability": probability,
                    "top_positive_features": positive,
                    "top_negative_features": negative,
                    "feature_importance": [{"feature_key": key, "importance": value} for key, value in ranked],
                    "knowledge_graph_evidence": knowledge_graph_evidence,
                    "news_contribution": news_contribution,
                    "community_contribution": community_contribution,
                }
            )
            if self.cache is not None:
                try:
                    await self.cache.set(cache_key, ai_explanation, _CACHE_TTL_SECONDS)
                except Exception:  # noqa: BLE001 — a broken cache backend must never block a good result
                    pass

        return ExplanationBundle(
            top_positive_features=positive,
            top_negative_features=negative,
            feature_importance=feature_importance,
            knowledge_graph_evidence=knowledge_graph_evidence,
            news_contribution=news_contribution,
            community_contribution=community_contribution,
            ai_explanation=ai_explanation,
        )

    async def explain_with_shap(
        self,
        subject_ref: str,
        market_key: str,
        predictor_output: PredictorOutput,
        probability: float,
        model: PredictionModelPort | None,
        features: dict[str, float],
        background: list[dict[str, float]],
    ) -> ExplanationBundle:
        """Milestone 9.1 — composes `explain()` (unchanged) and enriches the returned bundle with
        real SHAP values when both a `shap_explainer` was configured AND ``model`` is a fitted
        `PredictionModelPort` (never for the weighted predictors, which have no model to
        introspect — ``model=None`` there, and this degrades to plain `explain()`)."""
        bundle = await self.explain(subject_ref, market_key, predictor_output, probability)
        if self.shap_explainer is None or model is None:
            return bundle
        bundle.shap_explanation = self.shap_explainer.explain_instance(model, features, background)
        return bundle
