"""Real OpenAI adapter — calls the Chat Completions REST API directly
(``api.openai.com/v1/chat/completions``) rather than depending on the `openai` SDK, matching
`GeminiAdapter`'s and `ClaudeAdapter`'s own stated reasoning exactly: the REST contract is the
most stable integration surface. Implements the same provider-neutral
`TextIntelligenceProviderPort` both of those do, using the exact same shared system prompts
(`llm_prompts.py`) for the two methods that have one (`assess_prediction_context`/
`explain_football_prediction`) so no adapter can ever narrate under different instructions for
the same job — the LLM boundary this whole port exists to enforce
(`text_intelligence_provider.py`'s own module docstring) is identical regardless of which model
answers.

2026-08-30 — promoted to `real_adapter` (primary) in `TextIntelligenceRouter`'s production
wiring, with Gemini and Claude both demoted to `fallback_adapters`, per an explicit operator
decision made the same day a live Gemini quota exhaustion (429s, "You exceeded your current
quota") stalled prediction-generation narration mid-sweep. This has no effect on production
behavior until an operator actually adds a usable OpenAI API key via Provider Management — the
same activation gate every other real provider in this codebase already goes through
(`TextIntelligenceRouter._is_usable`); until then the router falls through to Claude, then
Gemini, then the mock adapter, exactly as it already did before this file existed.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import httpx

from modules.intelligence.infrastructure.llm_prompts import TITANIQ_FOOTBALL_ANALYST_V1, TITANIQ_GEMINI_REASONING_V1
from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
    TextIntelligenceRequestError,
)

if TYPE_CHECKING:
    from modules.intelligence.application.intelligence_monitoring_service import IntelligenceMetricsRecorder

ApiKeyGetter = Callable[[], Awaitable[str]]

# gpt-5.1 — a real cost/quality point distinct from Gemini's and Claude's own defaults
# (gemini_adapter.py/claude_adapter.py's _DEFAULT_MODEL), not just a drop-in vendor swap of the
# identical tier. Overridable via the constructor, same as every other adapter here.
_DEFAULT_MODEL = "gpt-5.1"


class OpenAIRequestError(TextIntelligenceRequestError):
    pass


def _strip_markdown_fence(text: str) -> str:
    """Cheap, honest safety net matching ClaudeAdapter's own — `response_format:
    {"type": "json_object"}` below is OpenAI's server-enforced JSON mode (closer to Gemini's
    `responseMimeType` than Claude's prompt-only convention), so this should rarely trigger, but
    costs nothing to keep as a backstop against a fenced response slipping through anyway."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
        stripped = stripped.strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


class OpenAIAdapter:
    provider_key = "openai"

    def __init__(
        self,
        get_api_key: ApiKeyGetter,
        model: str = _DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
        metrics_recorder: "IntelligenceMetricsRecorder | None" = None,
    ) -> None:
        self._get_api_key = get_api_key
        self._model = model
        # Same 30s reasoning as GeminiAdapter's/ClaudeAdapter's own comment: assess_prediction_
        # context's payload is the largest prompt this port sends, and TextIntelligenceRouter
        # retries once before falling further down the chain, so worst case is 2x this value.
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._metrics_recorder = metrics_recorder

    async def _generate(self, prompt: str, *, json_response: bool = False, system: str | None = None) -> str:
        try:
            api_key = await self._get_api_key()
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
            messages = []
            if system is not None:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            body: dict = {"model": self._model, "messages": messages}
            if json_response:
                body["response_format"] = {"type": "json_object"}
            if self._metrics_recorder is not None:
                self._metrics_recorder.record_openai_call()
            response = await self._client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            # OpenAI's key travels in a header (Authorization: Bearer), never a URL query param —
            # no leak risk from including the response body here, same as ClaudeAdapter's own
            # comment on why it can (unlike GeminiAdapter, whose key is a URL param).
            raise OpenAIRequestError(
                f"OpenAI request failed: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAIRequestError(f"OpenAI request failed: {type(exc).__name__} (network/transport error)") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise OpenAIRequestError(f"OpenAI returned an unexpected response shape: {exc}") from exc

    async def _generate_json(self, prompt: str, *, system: str | None = None) -> str:
        raw = await self._generate(prompt, json_response=True, system=system)
        return _strip_markdown_fence(raw)

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        prompt = (
            "Extract structured sports news events from the text below. event_type must be one "
            "of: transfer, injury, recovery, suspension, manager_change, formation_change, "
            "tactical_change, training_update, weather_report, travel_delay, stadium_change, "
            "match_postponement, player_availability, lineup_expectation. Respond with ONLY a "
            "JSON object with a single key \"events\" whose value is an array of objects with "
            "keys event_type, summary, entities (array of strings), confidence (0-1 float). "
            f"If there are no such events, respond with {{\"events\": []}}. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw).get("events", [])
        except json.JSONDecodeError as exc:
            raise OpenAIRequestError(f"OpenAI returned non-JSON for extract_events: {exc}") from exc
        return [
            ExtractedEvent(
                event_type=item.get("event_type", "unknown"),
                summary=item.get("summary", ""),
                entities=tuple(item.get("entities", [])),
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in parsed
        ]

    async def summarize(self, text: str, *, max_words: int = 120) -> str:
        prompt = f"Summarize the following text in at most {max_words} words:\n\n{text}"
        return await self._generate(prompt)

    async def explain(self, context: dict) -> str:
        prompt = (
            "Explain this sports prediction to a knowledgeable fan in 2-3 sentences, grounded "
            "only in the supporting data given — do not invent statistics or state a "
            f"probability yourself. Supporting data (JSON): {json.dumps(context)}"
        )
        return await self._generate(prompt)

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        prompt = f"Payload (JSON):\n{json.dumps(payload)}"
        raw = await self._generate_json(prompt, system=TITANIQ_GEMINI_REASONING_V1)
        return raw, "openai"

    async def explain_football_prediction(self, payload: dict) -> tuple[str, str]:
        prompt = f"Payload (JSON):\n{json.dumps(payload)}"
        raw = await self._generate_json(prompt, system=TITANIQ_FOOTBALL_ANALYST_V1)
        return raw, "openai"

    async def interpret_sentiment(self, text: str) -> str:
        prompt = (
            "Classify the overall sentiment of this sports-related community text as exactly "
            f"one word — positive, negative, or neutral. Text:\n\n{text}"
        )
        result = await self._generate(prompt)
        return result.strip().lower()

    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        prompt = (
            "Perform named entity recognition on the sports text below. Identify every player, "
            "team, competition, coach, venue, country, sponsor, and organization mention. "
            "Respond with ONLY a JSON object with a single key \"entities\" whose value is an "
            "array of objects with keys text, entity_type, confidence (0-1 float). If there are "
            f"none, respond with {{\"entities\": []}}. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw).get("entities", [])
        except json.JSONDecodeError as exc:
            raise OpenAIRequestError(f"OpenAI returned non-JSON for extract_entities: {exc}") from exc
        return [
            ExtractedEntity(
                text=item.get("text", ""),
                entity_type=item.get("entity_type", "unknown"),
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in parsed
        ]

    async def extract_relationships(self, text: str) -> list[ExtractedRelationship]:
        prompt = (
            "Extract subject-relation-object relationship triples between entities in the "
            "sports text below. Respond with ONLY a JSON object with a single key "
            "\"relationships\" whose value is an array of objects with keys subject, relation, "
            f"object, confidence (0-1 float). If there are none, respond with "
            f"{{\"relationships\": []}}. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw).get("relationships", [])
        except json.JSONDecodeError as exc:
            raise OpenAIRequestError(f"OpenAI returned non-JSON for extract_relationships: {exc}") from exc
        return [
            ExtractedRelationship(
                subject=item.get("subject", ""),
                relation=item.get("relation", ""),
                obj=item.get("object", ""),
                confidence=float(item.get("confidence", 0.0)),
            )
            for item in parsed
        ]

    async def classify_topics(self, text: str) -> list[str]:
        prompt = (
            "Classify the topics discussed in the sports text below. Respond with ONLY a JSON "
            "object with a single key \"topics\" whose value is an array of short lowercase "
            f"topic labels (e.g. \"injury\", \"transfer\"). Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            return list(json.loads(raw).get("topics", []))
        except json.JSONDecodeError as exc:
            raise OpenAIRequestError(f"OpenAI returned non-JSON for classify_topics: {exc}") from exc

    async def detect_language(self, text: str) -> str:
        prompt = f"Respond with only the ISO 639-1 two-letter language code of this text:\n\n{text}"
        result = await self._generate(prompt)
        return result.strip().lower()[:2]

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        prompt = (
            f"Extract the {limit} most salient key phrases from the sports text below. Respond "
            "with ONLY a JSON object with a single key \"phrases\" whose value is an array of "
            "objects with keys phrase, score (0-1 float), ordered by relevance descending. "
            f"Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw).get("phrases", [])
        except json.JSONDecodeError as exc:
            raise OpenAIRequestError(f"OpenAI returned non-JSON for extract_key_phrases: {exc}") from exc
        return [
            KeyPhrase(phrase=item.get("phrase", ""), score=float(item.get("score", 0.0)))
            for item in parsed[:limit]
        ]

    async def aclose(self) -> None:
        await self._client.aclose()
