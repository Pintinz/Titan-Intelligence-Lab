from __future__ import annotations

from dataclasses import dataclass

import pytest

from modules.intelligence.application.intelligence_retrieval_service import IntelligenceRetrievalService
from modules.intelligence.ports.retrieval import (
    IntelligenceRetrievalDocument,
    IntelligenceRetrievalQuery,
    IntelligenceRetrievalResult,
)
from modules.predictions.application.explainability_engine import ExplainabilityEngine
from modules.predictions.domain.explainability import ShapExplanation
from modules.predictions.ports.predictor import PredictorOutput


@dataclass
class _FakeRetrievalPort:
    modality: str
    documents: tuple[IntelligenceRetrievalDocument, ...] = ()

    async def retrieve(self, query: IntelligenceRetrievalQuery) -> IntelligenceRetrievalResult:
        return IntelligenceRetrievalResult(query=query, documents=self.documents, truncated=False)


@dataclass
class _EmptyTeamNamesResolver:
    async def team_names_for_match(self, subject_ref: str) -> tuple[str, ...]:
        return ()


@dataclass
class _FakeTextIntelligenceProvider:
    provider_key: str = "fake"
    last_context: dict | None = None

    async def explain(self, context: dict) -> str:
        self.last_context = context
        return f"explained {context['market_key']} at p={context['probability']}"


def _document(modality: str, text: str) -> IntelligenceRetrievalDocument:
    return IntelligenceRetrievalDocument(modality=modality, subject_ref="fixture-1", text=text, source="src", confidence=0.8)


@pytest.fixture
def retrieval_service():
    return IntelligenceRetrievalService(
        news=_FakeRetrievalPort(modality="news", documents=(_document("news", "Star striker ruled out with injury"),)),
        community=_FakeRetrievalPort(
            modality="community", documents=(_document("community", "Fans expect a tight, low-scoring match"),)
        ),
        knowledge_graph=_FakeRetrievalPort(
            modality="knowledge_graph", documents=(_document("knowledge_graph", "TeamA rivalry_with TeamB"),)
        ),
        ai_reports=_FakeRetrievalPort(modality="ai_reports", documents=()),
        team_names=_EmptyTeamNamesResolver(),
    )


@pytest.fixture
def text_intelligence():
    return _FakeTextIntelligenceProvider()


@pytest.fixture
def engine(retrieval_service, text_intelligence):
    return ExplainabilityEngine(retrieval=retrieval_service, text_intelligence=text_intelligence, top_n=3)


@pytest.mark.asyncio
async def test_explain_ranks_positive_and_negative_features(engine):
    output = PredictorOutput(
        raw_score=0.3,
        probability=0.6,
        value="positive",
        feature_contributions={"team_form": 0.5, "injuries": -0.4, "head_to_head": 0.2, "travel_fatigue": -0.1},
    )

    bundle = await engine.explain("fixture-1", "football.match_result", output, probability=0.62)

    assert bundle.top_positive_features == (("team_form", 0.5), ("head_to_head", 0.2))
    assert bundle.top_negative_features == (("injuries", -0.4), ("travel_fatigue", -0.1))


@pytest.mark.asyncio
async def test_explain_computes_normalized_feature_importance(engine):
    output = PredictorOutput(
        raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.6, "b": -0.4}
    )

    bundle = await engine.explain("fixture-1", "football.match_result", output, probability=0.55)

    assert bundle.feature_importance == pytest.approx({"a": 0.6, "b": 0.4})


@pytest.mark.asyncio
async def test_explain_handles_all_zero_contributions_without_division_error(engine):
    output = PredictorOutput(raw_score=0.0, probability=0.5, value="negative", feature_contributions={"a": 0.0})

    bundle = await engine.explain("fixture-1", "football.match_result", output, probability=0.5)

    assert bundle.feature_importance == {"a": 0.0}


@pytest.mark.asyncio
async def test_explain_splits_retrieval_documents_by_modality(engine):
    output = PredictorOutput(raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.1})

    bundle = await engine.explain("fixture-1", "football.match_result", output, probability=0.55)

    assert bundle.knowledge_graph_evidence == ("TeamA rivalry_with TeamB",)
    assert bundle.news_contribution == ("Star striker ruled out with injury",)
    assert bundle.community_contribution == ("Fans expect a tight, low-scoring match",)


@pytest.mark.asyncio
async def test_explain_forwards_ranked_context_to_text_intelligence_and_returns_its_explanation(
    engine, text_intelligence
):
    output = PredictorOutput(raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.1})

    bundle = await engine.explain("fixture-1", "football.match_result", output, probability=0.55)

    assert bundle.ai_explanation == "explained football.match_result at p=0.55"
    assert text_intelligence.last_context["top_positive_features"] == (("a", 0.1),)
    assert text_intelligence.last_context["knowledge_graph_evidence"] == ("TeamA rivalry_with TeamB",)


@dataclass
class _FakeShapExplainer:
    explanation: ShapExplanation
    last_call: dict | None = None

    def explain_instance(self, model, features, background):
        self.last_call = {"model": model, "features": features, "background": background}
        return self.explanation


@pytest.mark.asyncio
async def test_explain_with_shap_enriches_bundle_when_model_and_explainer_present(retrieval_service, text_intelligence):
    shap_explanation = ShapExplanation(local_shap_values={"a": 0.4}, global_importance={"a": 1.0}, base_value=0.5)
    fake_shap = _FakeShapExplainer(explanation=shap_explanation)
    engine = ExplainabilityEngine(
        retrieval=retrieval_service, text_intelligence=text_intelligence, top_n=3, shap_explainer=fake_shap
    )
    output = PredictorOutput(raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.1})

    bundle = await engine.explain_with_shap(
        "fixture-1", "football.match_result", output, 0.55, model=object(), features={"a": 1.0}, background=[{"a": 0.5}]
    )

    assert bundle.shap_explanation is shap_explanation
    assert bundle.ai_explanation == "explained football.match_result at p=0.55"  # explain() output preserved
    assert fake_shap.last_call["features"] == {"a": 1.0}


@pytest.mark.asyncio
async def test_explain_with_shap_without_explainer_configured_degrades_to_plain_explain(engine):
    output = PredictorOutput(raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.1})

    bundle = await engine.explain_with_shap(
        "fixture-1", "football.match_result", output, 0.55, model=object(), features={"a": 1.0}, background=[]
    )

    assert bundle.shap_explanation is None


@pytest.mark.asyncio
async def test_explain_with_shap_without_model_degrades_to_plain_explain(retrieval_service, text_intelligence):
    fake_shap = _FakeShapExplainer(explanation=ShapExplanation())
    engine = ExplainabilityEngine(
        retrieval=retrieval_service, text_intelligence=text_intelligence, top_n=3, shap_explainer=fake_shap
    )
    output = PredictorOutput(raw_score=0.1, probability=0.55, value="positive", feature_contributions={"a": 0.1})

    bundle = await engine.explain_with_shap(
        "fixture-1", "football.match_result", output, 0.55, model=None, features={"a": 1.0}, background=[]
    )

    assert bundle.shap_explanation is None
    assert fake_shap.last_call is None
