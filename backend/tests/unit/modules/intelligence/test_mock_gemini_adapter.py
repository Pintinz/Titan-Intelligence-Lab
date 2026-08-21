import json

import pytest

from modules.intelligence.infrastructure.mock_gemini_adapter import MockGeminiAdapter
from modules.predictions.infrastructure.football_explanation_schema import FootballExplanationSchema
from modules.predictions.infrastructure.gemini_reasoning_schema import GeminiReasoningResponseSchema


@pytest.mark.asyncio
async def test_extract_events_detects_injury_mentions():
    adapter = MockGeminiAdapter()

    events = await adapter.extract_events("Star striker suffers hamstring injury in training.")

    assert any(e.event_type == "injury" for e in events)


@pytest.mark.asyncio
async def test_extract_events_detects_transfer_mentions():
    adapter = MockGeminiAdapter()

    events = await adapter.extract_events("Club confirms the transfer signing of a new midfielder.")

    assert any(e.event_type == "transfer" for e in events)


@pytest.mark.asyncio
async def test_extract_events_empty_for_unrelated_text():
    adapter = MockGeminiAdapter()

    events = await adapter.extract_events("Fans gathered outside the ground before kickoff.")

    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,expected_event_type",
    [
        ("The player has recovered and returns to training this week.", "recovery"),
        ("The defender was suspended after receiving a red card.", "suspension"),
        ("The manager was sacked following a run of poor results.", "manager_change"),
        ("The coach switched to a new formation for the second half.", "formation_change"),
        ("Pundits discussed the tactic used to break down the defense.", "tactical_change"),
        ("The club held a training session ahead of the weekend fixture.", "training_update"),
        ("Heavy rain and storm warnings are forecast for matchday.", "weather_report"),
        ("The squad suffered a flight delay ahead of the away fixture.", "travel_delay"),
        ("The fixture saw a late stadium change due to safety concerns.", "stadium_change"),
        ("The match was postponed due to a waterlogged pitch.", "match_postponement"),
        ("The winger is doubtful for the weekend after a knock in training.", "player_availability"),
        ("Reports suggest the expected lineup will feature two changes.", "lineup_expectation"),
    ],
)
async def test_extract_events_covers_every_news_event_type(text, expected_event_type):
    adapter = MockGeminiAdapter()

    events = await adapter.extract_events(text)

    assert any(e.event_type == expected_event_type for e in events)


@pytest.mark.asyncio
async def test_summarize_truncates_to_max_words():
    adapter = MockGeminiAdapter()
    text = " ".join(f"word{i}" for i in range(200))

    summary = await adapter.summarize(text, max_words=10)

    assert len(summary.split()) <= 11  # 10 words + trailing "..."


@pytest.mark.asyncio
async def test_explain_references_top_features():
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain(
        {"feature_importance": [{"feature_key": "football.team.form_index_last5"}]}
    )

    assert "Form Index (Last 5)" in explanation


@pytest.mark.asyncio
async def test_explain_humanizes_namespaced_feature_keys():
    """Explanation text is user-facing narration — it must never leak a raw, dotted backend
    feature identifier like "football.fixture.form_shots_on_target_diff_last5" verbatim."""
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain(
        {"feature_importance": [{"feature_key": "football.fixture.form_shots_on_target_diff_last5"}]}
    )

    assert "football.fixture" not in explanation
    assert "Form Shots On Target Diff (Last 5)" in explanation


@pytest.mark.asyncio
async def test_explain_default_text_with_no_feature_importance():
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain({})

    assert explanation == "This verdict is grounded in the match's available data — no single factor dominates it."


@pytest.mark.asyncio
async def test_explain_includes_real_projected_probability():
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain(
        {
            "feature_importance": [{"feature_key": "football.fixture.expected_home_goals", "importance": 0.6}],
            "probability": 0.72,
        }
    )

    assert "Projected probability: 72%." in explanation


@pytest.mark.asyncio
async def test_explain_mentions_a_genuine_contradicting_factor():
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain(
        {
            "feature_importance": [
                {"feature_key": "football.fixture.expected_home_goals", "importance": 0.6},
                {"feature_key": "football.team.form_index_last5", "importance": -0.3},
            ],
        }
    )

    assert "Form Index (Last 5) pulls the other way but isn't enough to change the call." in explanation


@pytest.mark.asyncio
async def test_explain_omits_contradicting_clause_when_every_ranked_feature_is_positive():
    adapter = MockGeminiAdapter()

    explanation = await adapter.explain(
        {"feature_importance": [{"feature_key": "football.fixture.expected_home_goals", "importance": 0.6}]},
    )

    assert "pulls the other way" not in explanation


@pytest.mark.asyncio
async def test_interpret_sentiment_classifies_text():
    adapter = MockGeminiAdapter()

    assert await adapter.interpret_sentiment("Great win, the team looked strong and confident!") == "positive"
    assert await adapter.interpret_sentiment("Terrible loss, major injury doubt looms.") == "negative"
    assert await adapter.interpret_sentiment("The match is scheduled for Sunday.") == "neutral"


@pytest.mark.asyncio
async def test_extract_entities_finds_title_case_spans():
    adapter = MockGeminiAdapter()

    entities = await adapter.extract_entities("Erling Haaland scored twice for Manchester City.")

    texts = {e.text for e in entities}
    assert "Erling Haaland" in texts
    assert "Manchester City" in texts


@pytest.mark.asyncio
async def test_extract_entities_infers_team_type_from_keyword():
    adapter = MockGeminiAdapter()

    entities = await adapter.extract_entities("Liverpool FC announced the signing today.")

    liverpool = next(e for e in entities if e.text == "Liverpool FC")
    assert liverpool.entity_type == "team"


@pytest.mark.asyncio
async def test_extract_entities_infers_coach_type_from_keyword():
    adapter = MockGeminiAdapter()

    entities = await adapter.extract_entities("Pep Guardiola is the manager this season.")

    guardiola = next(e for e in entities if e.text == "Pep Guardiola")
    assert guardiola.entity_type == "coach"


@pytest.mark.asyncio
async def test_extract_entities_infers_venue_type_from_keyword():
    adapter = MockGeminiAdapter()

    entities = await adapter.extract_entities("The match was played at Wembley Stadium.")

    wembley = next(e for e in entities if e.text == "Wembley Stadium")
    assert wembley.entity_type == "venue"


@pytest.mark.asyncio
async def test_extract_entities_deduplicates_repeated_mentions():
    adapter = MockGeminiAdapter()

    entities = await adapter.extract_entities("Kylian Mbappe scored. Kylian Mbappe celebrated.")

    assert len([e for e in entities if e.text == "Kylian Mbappe"]) == 1


@pytest.mark.asyncio
async def test_extract_relationships_matches_known_phrase():
    adapter = MockGeminiAdapter()

    relationships = await adapter.extract_relationships("Neymar transferred to Real Madrid this summer.")

    assert any(
        r.subject == "Neymar" and r.relation == "transferred_to" and r.obj == "Real Madrid"
        for r in relationships
    )


@pytest.mark.asyncio
async def test_extract_relationships_empty_when_no_known_phrase():
    adapter = MockGeminiAdapter()

    assert await adapter.extract_relationships("The weather was pleasant.") == []


@pytest.mark.asyncio
async def test_classify_topics_matches_multiple_keywords():
    adapter = MockGeminiAdapter()

    topics = await adapter.classify_topics("The manager was sacked after the suspension controversy.")

    assert "manager_change" in topics
    assert "suspension" in topics


@pytest.mark.asyncio
async def test_classify_topics_empty_for_unrelated_text():
    adapter = MockGeminiAdapter()

    assert await adapter.classify_topics("The stadium concessions sell popcorn.") == []


@pytest.mark.asyncio
async def test_detect_language_defaults_to_english():
    adapter = MockGeminiAdapter()

    assert await adapter.detect_language("The team won the match yesterday.") == "en"


@pytest.mark.asyncio
async def test_detect_language_detects_spanish_marker_words():
    adapter = MockGeminiAdapter()

    assert await adapter.detect_language("El equipo gano el partido de la liga") == "es"


@pytest.mark.asyncio
async def test_detect_language_detects_french_marker_words():
    adapter = MockGeminiAdapter()

    assert await adapter.detect_language("Le match et les buts etaient superbes") == "fr"


@pytest.mark.asyncio
async def test_extract_key_phrases_ranks_by_frequency():
    adapter = MockGeminiAdapter()
    text = "injury injury injury transfer transfer tactics"

    phrases = await adapter.extract_key_phrases(text, limit=2)

    assert phrases[0].phrase == "injury"
    assert phrases[0].score > phrases[1].score


@pytest.mark.asyncio
async def test_extract_key_phrases_empty_for_only_stopwords():
    adapter = MockGeminiAdapter()

    assert await adapter.extract_key_phrases("the a an of in on") == []


@pytest.mark.asyncio
async def test_assess_prediction_context_returns_insufficient_context_when_no_evidence():
    """A market with zero accepted evidence items across every category must get
    INSUFFICIENT_CONTEXT, never a fabricated SUPPORTED/CHALLENGED verdict this mock has no way
    to make honestly."""
    adapter = MockGeminiAdapter()

    raw, _ = await adapter.assess_prediction_context({"context": {"news": [], "injuries": []}})
    parsed = GeminiReasoningResponseSchema.model_validate(json.loads(raw))

    assert parsed.prediction_review.status.value == "INSUFFICIENT_CONTEXT"
    assert parsed.prediction_reconsideration.direction.value == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_assess_prediction_context_reports_missing_categories_honestly():
    adapter = MockGeminiAdapter()

    raw, _ = await adapter.assess_prediction_context({"context": {"news": [], "injuries": []}})
    parsed = json.loads(raw)

    assert set(parsed["missing_context"]) == {"news", "injuries"}


@pytest.mark.asyncio
async def test_assess_prediction_context_never_claims_a_directional_read_with_real_evidence():
    """With genuine evidence present the mock still can't honestly judge direction — it must
    report NEUTRAL, never SUPPORTED/CHALLENGED, since it has no real reasoning capability."""
    adapter = MockGeminiAdapter()

    raw, _ = await adapter.assess_prediction_context(
        {"context": {"news": [{"source_id": "n1"}, {"source_id": "n2"}, {"source_id": "n3"}]}}
    )
    parsed = GeminiReasoningResponseSchema.model_validate(json.loads(raw))

    assert parsed.prediction_review.status.value == "NEUTRAL"


@pytest.mark.asyncio
async def test_assess_prediction_context_output_always_matches_the_strict_schema():
    adapter = MockGeminiAdapter()

    empty_raw, _ = await adapter.assess_prediction_context({"context": {}})
    populated_raw, _ = await adapter.assess_prediction_context(
        {"context": {"injuries": [{"source_id": "i1"}]}}
    )

    GeminiReasoningResponseSchema.model_validate(json.loads(empty_raw))
    GeminiReasoningResponseSchema.model_validate(json.loads(populated_raw))


@pytest.mark.asyncio
async def test_explain_football_prediction_output_matches_the_strict_schema():
    """Sports-Analyst Explainability Upgrade — the mock is what actually renders whenever the real
    Gemini adapter is unavailable (e.g. provider quota exhausted), so it must produce the full
    richer schema, not a degraded subset."""
    adapter = MockGeminiAdapter()
    payload = {
        "market": "Correct Score", "prediction": "2-1", "probability": 0.107, "titan_iq_confidence": 0.57,
        "market_reasoning_kind": "correct_score",
        "key_reasons": [{"rank": 1, "feature": "football.fixture.expected_home_goals", "football_concept": "modeled home scoring rate", "contribution": 1.15, "direction": "supports"}],
        "counter_signals": [],
        "context": [{"type": "injuries", "description": "1 verified pre-cutoff injuries item(s)", "model_contribution": 0.0, "role": "context_only"}],
        "evidence_items": {"injuries": [{"source_id": "inj-1", "summary": "Out (hamstring)", "entity_ref": "team-1"}], "news": [], "lineups": []},
        "scoreline": {
            "selected_score": "2-1", "selected_probability": 0.107, "expected_home_goals": 1.7, "expected_away_goals": 1.2,
            "alternatives": [{"score": "1-1", "probability": 0.098}],
        },
    }

    raw, _ = await adapter.explain_football_prediction(payload)
    parsed = FootballExplanationSchema.model_validate(json.loads(raw))

    assert parsed.scoreline_reasoning is not None
    assert parsed.injury_narration[0].source_id == "inj-1"
    assert "context, not a material driver" in parsed.injury_narration[0].analysis
    assert "57%" in parsed.confidence_explanation and "11%" in parsed.confidence_explanation


@pytest.mark.asyncio
async def test_explain_football_prediction_omits_scoreline_for_non_correct_score_markets():
    adapter = MockGeminiAdapter()
    payload = {
        "market": "Match Winner", "prediction": "Home Win", "probability": 0.5, "titan_iq_confidence": 0.6,
        "market_reasoning_kind": "match_winner", "key_reasons": [], "counter_signals": [], "context": [],
        "evidence_items": {},
    }

    raw, _ = await adapter.explain_football_prediction(payload)
    parsed = FootballExplanationSchema.model_validate(json.loads(raw))

    assert parsed.scoreline_reasoning is None


@pytest.mark.asyncio
async def test_explain_football_prediction_context_quality_is_honest_when_no_evidence():
    adapter = MockGeminiAdapter()
    payload = {
        "market": "Match Winner", "prediction": "Home Win", "probability": 0.5, "titan_iq_confidence": 0.6,
        "market_reasoning_kind": "match_winner", "key_reasons": [], "counter_signals": [], "context": [],
        "evidence_items": {"injuries": [], "news": [], "lineups": []},
    }

    raw, _ = await adapter.explain_football_prediction(payload)
    parsed = FootballExplanationSchema.model_validate(json.loads(raw))

    assert "No verified" in parsed.context_quality
