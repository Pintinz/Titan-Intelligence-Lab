"""Tests the real Gemini HTTP adapter against a mocked transport — the actual adapter code
(URL construction, request body, JSON parsing) runs; only the network is faked
(docs/decisions.md ADR-008 pattern, same as tests/unit/modules/sports/test_api_sports_adapter.py
and tests/unit/modules/intelligence/test_rss_news_provider.py)."""

from __future__ import annotations

import json

import httpx
import pytest

from modules.intelligence.application.intelligence_monitoring_service import IntelligenceMetricsRecorder
from modules.intelligence.infrastructure.gemini_adapter import GeminiAdapter, GeminiRequestError


async def _get_key() -> str:
    return "test-api-key"


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _gemini_text_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})


@pytest.mark.asyncio
async def test_extract_events_parses_json_response():
    payload = [{"event_type": "injury", "summary": "Player injured.", "entities": ["p1"], "confidence": 0.8}]

    def handler(request):
        return _gemini_text_response(json.dumps(payload))

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    events = await adapter.extract_events("Some injury news.")

    assert len(events) == 1
    assert events[0].event_type == "injury"
    assert events[0].entities == ("p1",)
    assert events[0].confidence == 0.8


@pytest.mark.asyncio
async def test_extract_events_raises_on_non_json_response():
    def handler(request):
        return _gemini_text_response("not json")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.extract_events("Some text.")


@pytest.mark.asyncio
async def test_summarize_returns_plain_text():
    def handler(request):
        return _gemini_text_response("A short summary.")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.summarize("Long text here.", max_words=10)

    assert result == "A short summary."


@pytest.mark.asyncio
async def test_explain_returns_plain_text():
    def handler(request):
        return _gemini_text_response("This prediction is driven by recent form.")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.explain({"feature_importance": []})

    assert "driven by recent form" in result


@pytest.mark.asyncio
async def test_interpret_sentiment_normalizes_casing():
    def handler(request):
        return _gemini_text_response("  POSITIVE  ")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.interpret_sentiment("Great win today.")

    assert result == "positive"


@pytest.mark.asyncio
async def test_extract_entities_parses_json_response():
    payload = [{"text": "Erling Haaland", "entity_type": "player", "confidence": 0.9}]

    def handler(request):
        return _gemini_text_response(json.dumps(payload))

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    entities = await adapter.extract_entities("Erling Haaland scored.")

    assert entities[0].text == "Erling Haaland"
    assert entities[0].entity_type == "player"


@pytest.mark.asyncio
async def test_extract_entities_raises_on_non_json_response():
    def handler(request):
        return _gemini_text_response("not json")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.extract_entities("Some text.")


@pytest.mark.asyncio
async def test_extract_relationships_parses_json_response():
    payload = [{"subject": "Mbappe", "relation": "transferred_to", "object": "Real Madrid", "confidence": 0.7}]

    def handler(request):
        return _gemini_text_response(json.dumps(payload))

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    relationships = await adapter.extract_relationships("Mbappe transferred to Real Madrid.")

    assert relationships[0].subject == "Mbappe"
    assert relationships[0].relation == "transferred_to"
    assert relationships[0].obj == "Real Madrid"


@pytest.mark.asyncio
async def test_extract_relationships_raises_on_non_json_response():
    def handler(request):
        return _gemini_text_response("not json")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.extract_relationships("Some text.")


@pytest.mark.asyncio
async def test_classify_topics_parses_json_array():
    def handler(request):
        return _gemini_text_response(json.dumps(["injury", "transfer"]))

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    topics = await adapter.classify_topics("Injury and transfer news.")

    assert topics == ["injury", "transfer"]


@pytest.mark.asyncio
async def test_classify_topics_raises_on_non_json_response():
    def handler(request):
        return _gemini_text_response("not json")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.classify_topics("Some text.")


@pytest.mark.asyncio
async def test_detect_language_normalizes_to_two_letter_code():
    def handler(request):
        return _gemini_text_response("EN")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.detect_language("The team won.")

    assert result == "en"


@pytest.mark.asyncio
async def test_extract_key_phrases_parses_json_and_respects_limit():
    payload = [{"phrase": "injury", "score": 0.9}, {"phrase": "transfer", "score": 0.7}, {"phrase": "tactics", "score": 0.5}]

    def handler(request):
        return _gemini_text_response(json.dumps(payload))

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    phrases = await adapter.extract_key_phrases("Some sports text.", limit=2)

    assert len(phrases) == 2
    assert phrases[0].phrase == "injury"


@pytest.mark.asyncio
async def test_extract_key_phrases_raises_on_non_json_response():
    def handler(request):
        return _gemini_text_response("not json")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.extract_key_phrases("Some text.")


@pytest.mark.asyncio
async def test_generate_wraps_http_error():
    def handler(request):
        return httpx.Response(500, text="server error")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.summarize("Some text.")


@pytest.mark.asyncio
async def test_generate_wraps_malformed_candidates_shape():
    def handler(request):
        return httpx.Response(200, json={"candidates": []})

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(GeminiRequestError):
        await adapter.summarize("Some text.")


@pytest.mark.asyncio
async def test_aclose_closes_client():
    closed = {"value": False}

    class TrackingClient(httpx.AsyncClient):
        async def aclose(self):
            closed["value"] = True
            await super().aclose()

    adapter = GeminiAdapter(
        get_api_key=_get_key, client=TrackingClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )

    await adapter.aclose()

    assert closed["value"] is True


@pytest.mark.asyncio
async def test_default_model_used_when_not_specified():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        return _gemini_text_response("ok")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.summarize("text")

    assert "gemini-3.6-flash" in captured["url"]


# -- POST-M24 Phase 2: gemini_call_count metric --------------------------------------------------


@pytest.mark.asyncio
async def test_real_call_increments_the_metrics_recorder():
    def handler(request):
        return _gemini_text_response("A short summary.")

    recorder = IntelligenceMetricsRecorder()
    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler), metrics_recorder=recorder)

    await adapter.summarize("Some text.")

    assert recorder.gemini_call_count == 1


@pytest.mark.asyncio
async def test_every_public_method_increments_the_metric_once_per_call():
    def handler(request):
        return _gemini_text_response(json.dumps([]))

    recorder = IntelligenceMetricsRecorder()
    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler), metrics_recorder=recorder)

    await adapter.extract_events("text")
    await adapter.extract_entities("text")
    await adapter.classify_topics("text")

    assert recorder.gemini_call_count == 3


@pytest.mark.asyncio
async def test_a_failed_real_call_still_increments_the_metric():
    """A failed real call still consumed quota/cost — it must still count, unlike a cache hit or
    a reused analysis, which never reach the network at all."""
    def handler(request):
        return httpx.Response(500, text="server error")

    recorder = IntelligenceMetricsRecorder()
    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler), metrics_recorder=recorder)

    with pytest.raises(GeminiRequestError):
        await adapter.summarize("Some text.")

    assert recorder.gemini_call_count == 1


@pytest.mark.asyncio
async def test_assess_prediction_context_returns_raw_gemini_text():
    """The Gemini Prediction Reasoning Engine's adapter method stays a pure text-in/text-out
    passthrough — the JSON payload it returns is validated by
    `GeminiReasoningResponseSchema`/`ContextualReasoningService`, not the adapter itself."""
    raw = '{"prediction_review": {"status": "SUPPORTED"}}'

    def handler(request):
        return _gemini_text_response(raw)

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    result, source = await adapter.assess_prediction_context({"sport": "football", "context": {}})

    assert result == raw
    assert source == "gemini"


@pytest.mark.asyncio
async def test_assess_prediction_context_includes_the_payload_in_the_request():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _gemini_text_response("{}")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.assess_prediction_context({"sport": "football", "market": "football.match_winner"})

    prompt_text = captured["body"]["contents"][0]["parts"][0]["text"]
    assert "football.match_winner" in prompt_text
    assert "NOT the primary statistical prediction model" in prompt_text


@pytest.mark.asyncio
async def test_no_recorder_configured_does_not_raise():
    def handler(request):
        return _gemini_text_response("ok")

    adapter = GeminiAdapter(get_api_key=_get_key, client=_client_for(handler))  # no metrics_recorder

    result = await adapter.summarize("text")

    assert result == "ok"
