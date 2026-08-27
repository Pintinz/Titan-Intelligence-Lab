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

_DEFAULT_MODEL = "gemini-3.6-flash"

# Re-exported for backward compatibility — the actual text now lives in llm_prompts.py, shared
# with ClaudeAdapter, so the two adapters can never drift into different instructions for the
# same job. Nothing in this codebase imports these two names from here (confirmed via grep before
# the move), but kept as aliases rather than removed outright in case an external caller does.
__all__ = [
    "GeminiAdapter",
    "GeminiRequestError",
    "TITANIQ_GEMINI_REASONING_V1",
    "TITANIQ_FOOTBALL_ANALYST_V1",
]


class GeminiRequestError(TextIntelligenceRequestError):
    pass


class GeminiAdapter:
    provider_key = "gemini"

    def __init__(
        self,
        get_api_key: ApiKeyGetter,
        model: str = _DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
        metrics_recorder: "IntelligenceMetricsRecorder | None" = None,
    ) -> None:
        self._get_api_key = get_api_key
        self._model = model
        # 30s (not the previous 20s): assess_prediction_context's evidence payload is much larger
        # than the other methods' prompts, and Gemini genuinely needs more time to generate its
        # structured JSON response for it — the shorter timeout was causing a real, reproducible
        # ReadTimeout on every live call. Kept well under 45s deliberately: TextIntelligenceRouter
        # now retries a failed call once before falling back to mock, so worst case is 2x this
        # value — needs to stay inside the frontend's 60s request budget with headroom to spare.
        self._client = client or httpx.AsyncClient(timeout=30.0)
        # POST-M24 Phase 2: `gemini_call_count` must reflect real outbound requests, not cache
        # hits/reused analyses/failed preflight checks — so it's incremented here, at the one
        # choke point every public method on this adapter routes through, immediately before the
        # network call actually goes out (a failed real call still consumed quota/cost, so it
        # still counts). `None` (the default) means "don't track" — every existing caller/test
        # that constructs this adapter without a recorder keeps working unchanged.
        self._metrics_recorder = metrics_recorder

    async def _generate(self, prompt: str, *, json_response: bool = False) -> str:
        try:
            api_key = await self._get_api_key()
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent"
            body = {"contents": [{"parts": [{"text": prompt}]}]}
            if json_response:
                body["generationConfig"] = {"responseMimeType": "application/json"}
            if self._metrics_recorder is not None:
                self._metrics_recorder.record_gemini_call()
            response = await self._client.post(url, params={"key": api_key}, json=body)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except httpx.HTTPStatusError as exc:
            # Built from status_code/response text only, never str(exc) — the API key travels as
            # a URL query param (line above), and httpx's default HTTPStatusError message embeds
            # the full request URL, which would otherwise leak the credential into this (and every
            # caller's) error message/logs.
            raise GeminiRequestError(
                f"Gemini request failed: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise GeminiRequestError(f"Gemini request failed: {type(exc).__name__} (network/transport error)") from exc
        except (KeyError, IndexError, ValueError) as exc:
            # Parsing errors come from the response body only, never the request URL — safe to
            # include str(exc) here.
            raise GeminiRequestError(f"Gemini returned an unexpected response shape: {exc}") from exc

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

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        prompt = f"{TITANIQ_GEMINI_REASONING_V1}\n\nPayload (JSON):\n{json.dumps(payload)}"
        return await self._generate(prompt, json_response=True), "gemini"

    async def explain_football_prediction(self, payload: dict) -> tuple[str, str]:
        prompt = f"{TITANIQ_FOOTBALL_ANALYST_V1}\n\nPayload (JSON):\n{json.dumps(payload)}"
        return await self._generate(prompt, json_response=True), "gemini"

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
