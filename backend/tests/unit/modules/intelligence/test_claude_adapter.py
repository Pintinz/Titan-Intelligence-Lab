"""Tests the real Claude HTTP adapter against a mocked transport — the actual adapter code
(URL construction, request body, JSON parsing) runs; only the network is faked, mirroring
test_gemini_adapter.py's own established pattern (docs/decisions.md ADR-008)."""

from __future__ import annotations

import json

import httpx
import pytest

from modules.intelligence.application.intelligence_monitoring_service import IntelligenceMetricsRecorder
from modules.intelligence.infrastructure.claude_adapter import ClaudeAdapter, ClaudeRequestError


async def _get_key() -> str:
    return "test-api-key"


def _client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _claude_text_response(text: str) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


@pytest.mark.asyncio
async def test_extract_events_parses_json_response():
    payload = [{"event_type": "injury", "summary": "Player injured.", "entities": ["p1"], "confidence": 0.8}]

    def handler(request):
        return _claude_text_response(json.dumps(payload))

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    events = await adapter.extract_events("Some injury news.")

    assert len(events) == 1
    assert events[0].event_type == "injury"
    assert events[0].entities == ("p1",)
    assert events[0].confidence == 0.8


@pytest.mark.asyncio
async def test_extract_events_strips_a_markdown_fence_if_present():
    """Claude has no server-enforced JSON-only mode (unlike Gemini's responseMimeType) — this is
    the one real behavioral difference the adapter must handle even though the prompt already
    instructs against it."""
    payload = [{"event_type": "transfer", "summary": "Signed.", "entities": [], "confidence": 0.6}]

    def handler(request):
        return _claude_text_response(f"```json\n{json.dumps(payload)}\n```")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    events = await adapter.extract_events("Some transfer news.")

    assert len(events) == 1
    assert events[0].event_type == "transfer"


@pytest.mark.asyncio
async def test_extract_events_raises_on_non_json_response():
    def handler(request):
        return _claude_text_response("not json")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ClaudeRequestError):
        await adapter.extract_events("Some text.")


@pytest.mark.asyncio
async def test_summarize_returns_plain_text():
    def handler(request):
        return _claude_text_response("A short summary.")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.summarize("Long text here.", max_words=10)

    assert result == "A short summary."


@pytest.mark.asyncio
async def test_explain_returns_plain_text():
    def handler(request):
        return _claude_text_response("This prediction is driven by recent form.")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.explain({"feature_importance": []})

    assert "driven by recent form" in result


@pytest.mark.asyncio
async def test_interpret_sentiment_normalizes_casing():
    def handler(request):
        return _claude_text_response("  POSITIVE  ")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.interpret_sentiment("Great win today.")

    assert result == "positive"


@pytest.mark.asyncio
async def test_extract_entities_parses_json_response():
    payload = [{"text": "Erling Haaland", "entity_type": "player", "confidence": 0.9}]

    def handler(request):
        return _claude_text_response(json.dumps(payload))

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    entities = await adapter.extract_entities("Erling Haaland scored.")

    assert entities[0].text == "Erling Haaland"
    assert entities[0].entity_type == "player"


@pytest.mark.asyncio
async def test_extract_relationships_parses_json_response():
    payload = [{"subject": "Mbappe", "relation": "transferred_to", "object": "Real Madrid", "confidence": 0.7}]

    def handler(request):
        return _claude_text_response(json.dumps(payload))

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    relationships = await adapter.extract_relationships("Mbappe transferred to Real Madrid.")

    assert relationships[0].subject == "Mbappe"
    assert relationships[0].obj == "Real Madrid"


@pytest.mark.asyncio
async def test_classify_topics_parses_json_array():
    def handler(request):
        return _claude_text_response(json.dumps(["injury", "transfer"]))

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    topics = await adapter.classify_topics("Injury and transfer news.")

    assert topics == ["injury", "transfer"]


@pytest.mark.asyncio
async def test_detect_language_normalizes_to_two_letter_code():
    def handler(request):
        return _claude_text_response("EN")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    result = await adapter.detect_language("The team won.")

    assert result == "en"


@pytest.mark.asyncio
async def test_extract_key_phrases_parses_json_and_respects_limit():
    payload = [{"phrase": "injury", "score": 0.9}, {"phrase": "transfer", "score": 0.7}, {"phrase": "tactics", "score": 0.5}]

    def handler(request):
        return _claude_text_response(json.dumps(payload))

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    phrases = await adapter.extract_key_phrases("Some sports text.", limit=2)

    assert len(phrases) == 2
    assert phrases[0].phrase == "injury"


@pytest.mark.asyncio
async def test_generate_wraps_http_error():
    def handler(request):
        return httpx.Response(500, text="server error")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ClaudeRequestError):
        await adapter.summarize("Some text.")


@pytest.mark.asyncio
async def test_generate_wraps_malformed_content_shape():
    def handler(request):
        return httpx.Response(200, json={"content": []})

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    with pytest.raises(ClaudeRequestError):
        await adapter.summarize("Some text.")


@pytest.mark.asyncio
async def test_aclose_closes_client():
    closed = {"value": False}

    class TrackingClient(httpx.AsyncClient):
        async def aclose(self):
            closed["value"] = True
            await super().aclose()

    adapter = ClaudeAdapter(
        get_api_key=_get_key, client=TrackingClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )

    await adapter.aclose()

    assert closed["value"] is True


@pytest.mark.asyncio
async def test_default_model_used_when_not_specified():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _claude_text_response("ok")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.summarize("text")

    assert captured["body"]["model"] == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_api_key_travels_in_the_header_not_the_url():
    """Unlike Gemini's URL query-param key, Claude's key must never appear in the request URL —
    confirmed directly against the mocked request, not just asserted in a comment."""
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return _claude_text_response("ok")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.summarize("text")

    assert "test-api-key" not in captured["url"]
    assert captured["headers"]["x-api-key"] == "test-api-key"


# -- News Intelligence audit (2026-08-27): claude_call_count metric ------------------------------


@pytest.mark.asyncio
async def test_real_call_increments_the_metrics_recorder():
    def handler(request):
        return _claude_text_response("A short summary.")

    recorder = IntelligenceMetricsRecorder()
    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler), metrics_recorder=recorder)

    await adapter.summarize("Some text.")

    assert recorder.claude_call_count == 1
    assert recorder.gemini_call_count == 0  # never conflated with Gemini's own counter


@pytest.mark.asyncio
async def test_a_failed_real_call_still_increments_the_metric():
    def handler(request):
        return httpx.Response(500, text="server error")

    recorder = IntelligenceMetricsRecorder()
    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler), metrics_recorder=recorder)

    with pytest.raises(ClaudeRequestError):
        await adapter.summarize("Some text.")

    assert recorder.claude_call_count == 1


@pytest.mark.asyncio
async def test_assess_prediction_context_returns_raw_claude_text():
    raw = '{"prediction_review": {"status": "SUPPORTED"}}'

    def handler(request):
        return _claude_text_response(raw)

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    result, source = await adapter.assess_prediction_context({"sport": "football", "context": {}})

    assert result == raw
    assert source == "claude"


@pytest.mark.asyncio
async def test_assess_prediction_context_uses_the_shared_prompt_as_a_system_message():
    """Same instructions as GeminiAdapter's own — sent as Claude's dedicated `system` field, not
    concatenated into the user message, but textually identical (llm_prompts.py is the one shared
    source, imported by both adapters) so the two providers can never narrate under different
    rules for the same job."""
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _claude_text_response("{}")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.assess_prediction_context({"sport": "football", "market": "football.match_winner"})

    assert "NOT the primary statistical prediction model" in captured["body"]["system"]
    assert "football.match_winner" in captured["body"]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_explain_football_prediction_uses_the_football_analyst_prompt():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _claude_text_response("{}")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))

    await adapter.explain_football_prediction({"market_reasoning_kind": "match_winner"})

    assert "TitanIQ's football sports analyst" in captured["body"]["system"]


@pytest.mark.asyncio
async def test_no_recorder_configured_does_not_raise():
    def handler(request):
        return _claude_text_response("ok")

    adapter = ClaudeAdapter(get_api_key=_get_key, client=_client_for(handler))  # no metrics_recorder

    result = await adapter.summarize("text")

    assert result == "ok"
