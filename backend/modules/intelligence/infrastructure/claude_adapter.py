"""Real Claude (Anthropic) adapter — calls the Messages API directly
(``api.anthropic.com/v1/messages``) rather than depending on the `anthropic` SDK, matching
`GeminiAdapter`'s own stated reasoning exactly: "the REST contract is the most stable integration
surface." Implements the same provider-neutral `TextIntelligenceProviderPort` Gemini does, using
the exact same shared system prompts (`llm_prompts.py`) for the two methods that have one
(`assess_prediction_context`/`explain_football_prediction`) so the two adapters can never narrate
under different instructions for the same job — the LLM boundary this whole port exists to
enforce (`text_intelligence_provider.py`'s own module docstring) is identical regardless of which
model answers.

Correct Score / News Intelligence audit (2026-08-27): built as a second real provider for
`TextIntelligenceRouter`'s fallback chain, not a replacement for Gemini — see that module's own
docstring for why (a live-observed Gemini quota exhaustion during this session's own verification
run, 36 of 37 real calls returning HTTP 429). Registering "claude" as a real credentialed provider
is a separate, later step (`scripts/import_claude_credential_from_env.py`) — this adapter has no
effect on production behavior until an operator actually adds a usable Anthropic API key via
Provider Management, the same activation gate every other real provider in this codebase already
goes through.
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

# claude-sonnet-5 — the current Sonnet-tier model id, a real cost/quality point distinct from
# Gemini's own default (gemini_adapter.py's _DEFAULT_MODEL), not just a drop-in vendor swap of
# the identical tier.
_DEFAULT_MODEL = "claude-sonnet-5"
_ANTHROPIC_API_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


class ClaudeRequestError(TextIntelligenceRequestError):
    pass


def _strip_markdown_fence(text: str) -> str:
    """Claude, unlike Gemini's `responseMimeType: application/json`, has no server-enforced
    JSON-only response mode — the prompts already instruct "no markdown fences" (both shared
    prompts and every per-method prompt below), but this is a cheap, honest safety net for the
    rare case a fenced response slips through anyway, not a silent tolerance of prompt drift."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
        stripped = stripped.strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


class ClaudeAdapter:
    provider_key = "claude"

    def __init__(
        self,
        get_api_key: ApiKeyGetter,
        model: str = _DEFAULT_MODEL,
        client: httpx.AsyncClient | None = None,
        metrics_recorder: "IntelligenceMetricsRecorder | None" = None,
    ) -> None:
        self._get_api_key = get_api_key
        self._model = model
        # Same 30s reasoning as GeminiAdapter's own comment: assess_prediction_context's payload
        # is the largest prompt this port sends, and TextIntelligenceRouter retries once before
        # falling further down the chain, so worst case is 2x this value per adapter tried.
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._metrics_recorder = metrics_recorder

    async def _generate(self, prompt: str, *, system: str | None = None) -> str:
        try:
            api_key = await self._get_api_key()
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_API_VERSION,
                "content-type": "application/json",
            }
            body: dict = {
                "model": self._model,
                "max_tokens": _DEFAULT_MAX_TOKENS,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system is not None:
                body["system"] = system
            if self._metrics_recorder is not None:
                self._metrics_recorder.record_claude_call()
            response = await self._client.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
        except httpx.HTTPStatusError as exc:
            # Claude's key travels in a header (x-api-key), never a URL query param — no leak risk
            # from including the response body here, unlike GeminiAdapter's own comment on why it
            # can't include str(exc) freely.
            raise ClaudeRequestError(
                f"Claude request failed: HTTP {exc.response.status_code} — {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ClaudeRequestError(f"Claude request failed: {type(exc).__name__} (network/transport error)") from exc
        except (KeyError, IndexError, ValueError) as exc:
            raise ClaudeRequestError(f"Claude returned an unexpected response shape: {exc}") from exc

    async def _generate_json(self, prompt: str, *, system: str | None = None) -> str:
        raw = await self._generate(prompt, system=system)
        return _strip_markdown_fence(raw)

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        prompt = (
            "Extract structured sports news events from the text below. event_type must be one "
            "of: transfer, injury, recovery, suspension, manager_change, formation_change, "
            "tactical_change, training_update, weather_report, travel_delay, stadium_change, "
            "match_postponement, player_availability, lineup_expectation. Respond with ONLY a "
            "JSON array of objects with keys event_type, summary, entities (array of strings), "
            "confidence (0-1 float) — no prose, no markdown fences. "
            f"If there are no such events, respond with []. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeRequestError(f"Claude returned non-JSON for extract_events: {exc}") from exc
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
        return raw, "claude"

    async def explain_football_prediction(self, payload: dict) -> tuple[str, str]:
        prompt = f"Payload (JSON):\n{json.dumps(payload)}"
        raw = await self._generate_json(prompt, system=TITANIQ_FOOTBALL_ANALYST_V1)
        return raw, "claude"

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
            "Respond with ONLY a JSON array of objects with keys text, entity_type, confidence "
            f"(0-1 float) — no prose, no markdown fences. If there are none, respond with []. "
            f"Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeRequestError(f"Claude returned non-JSON for extract_entities: {exc}") from exc
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
            "sports text below. Respond with ONLY a JSON array of objects with keys subject, "
            "relation, object, confidence (0-1 float) — no prose, no markdown fences. If there "
            f"are none, respond with []. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeRequestError(f"Claude returned non-JSON for extract_relationships: {exc}") from exc
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
            "array of short lowercase topic labels (e.g. \"injury\", \"transfer\") — no prose, "
            f"no markdown fences. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            return list(json.loads(raw))
        except json.JSONDecodeError as exc:
            raise ClaudeRequestError(f"Claude returned non-JSON for classify_topics: {exc}") from exc

    async def detect_language(self, text: str) -> str:
        prompt = f"Respond with only the ISO 639-1 two-letter language code of this text:\n\n{text}"
        result = await self._generate(prompt)
        return result.strip().lower()[:2]

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        prompt = (
            f"Extract the {limit} most salient key phrases from the sports text below. Respond "
            "with ONLY a JSON array of objects with keys phrase, score (0-1 float), ordered by "
            f"relevance descending — no prose, no markdown fences. Text:\n\n{text}"
        )
        raw = await self._generate_json(prompt)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ClaudeRequestError(f"Claude returned non-JSON for extract_key_phrases: {exc}") from exc
        return [
            KeyPhrase(phrase=item.get("phrase", ""), score=float(item.get("score", 0.0)))
            for item in parsed[:limit]
        ]

    async def aclose(self) -> None:
        await self._client.aclose()
