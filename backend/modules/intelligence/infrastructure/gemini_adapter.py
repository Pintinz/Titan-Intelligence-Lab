"""Real Gemini adapter — calls the Gemini REST API directly
(``generativelanguage.googleapis.com``) rather than depending on a specific SDK version, since
the REST contract is the most stable integration surface. Genuine HTTP-calling code; the exact
prompt wording may need tuning once exercised against live responses (docs/roadmap.md Milestone
13 wires this into the real News Intelligence pipeline) — the request/auth/parsing plumbing
here does not change either way.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

import httpx

from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
)

ApiKeyGetter = Callable[[], Awaitable[str]]

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiRequestError(RuntimeError):
    pass


class GeminiAdapter:
    provider_key = "gemini"

    def __init__(
        self,
        get_api_key: ApiKeyGetter,
        model: str = _DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._get_api_key = get_api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=20.0)

    async def _generate(self, prompt: str, *, json_response: bool = False) -> str:
        try:
            api_key = await self._get_api_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            if json_response:
                body["generationConfig"] = {"responseMimeType": "application/json"}
            response = await self._client.post(url, params={"key": api_key}, json=body)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise GeminiRequestError(f"Gemini request failed: {exc}") from exc

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        prompt = (
            "Extract structured sports news events from the text below. event_type must be one "
            "of: transfer, injury, recovery, suspension, manager_change, formation_change, "
            "tactical_change, training_update, weather_report, travel_delay, stadium_change, "
            "match_postponement, player_availability, lineup_expectation. Respond as a JSON "
            "array of objects with keys event_type, summary, entities (array of strings), "
            "confidence (0-1 float). "
            f"If there are no such events, respond with []. Text:\n\n{text}"
        )
        raw = await self._generate(prompt, json_response=True)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiRequestError(f"Gemini returned non-JSON for extract_events: {exc}") from exc
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
            "Respond as a JSON array of objects with keys text, entity_type, confidence "
            f"(0-1 float). If there are none, respond with []. Text:\n\n{text}"
        )
        raw = await self._generate(prompt, json_response=True)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiRequestError(f"Gemini returned non-JSON for extract_entities: {exc}") from exc
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
            "sports text below. Respond as a JSON array of objects with keys subject, "
            "relation, object, confidence (0-1 float). If there are none, respond with []. "
            f"Text:\n\n{text}"
        )
        raw = await self._generate(prompt, json_response=True)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiRequestError(f"Gemini returned non-JSON for extract_relationships: {exc}") from exc
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
            "Classify the topics discussed in the sports text below. Respond as a JSON array "
            f"of short lowercase topic labels (e.g. \"injury\", \"transfer\"). Text:\n\n{text}"
        )
        raw = await self._generate(prompt, json_response=True)
        try:
            return list(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise GeminiRequestError(f"Gemini returned non-JSON for classify_topics: {exc}") from exc

    async def detect_language(self, text: str) -> str:
        prompt = f"Respond with only the ISO 639-1 two-letter language code of this text:\n\n{text}"
        result = await self._generate(prompt)
        return result.strip().lower()[:2]

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        prompt = (
            f"Extract the {limit} most salient key phrases from the sports text below. Respond "
            "as a JSON array of objects with keys phrase, score (0-1 float), ordered by "
            f"relevance descending. Text:\n\n{text}"
        )
        raw = await self._generate(prompt, json_response=True)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GeminiRequestError(f"Gemini returned non-JSON for extract_key_phrases: {exc}") from exc
        return [
            KeyPhrase(phrase=item.get("phrase", ""), score=float(item.get("score", 0.0)))
            for item in parsed[:limit]
        ]

    async def aclose(self) -> None:
        await self._client.aclose()
