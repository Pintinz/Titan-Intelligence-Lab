"""TextIntelligenceRouter — the real/mock resolution `SportsProviderRouter` already does for
sports data, applied to the text-intelligence port. `get_text_intelligence_provider()` used to
hardcode `MockGeminiAdapter()` permanently (docs/decisions.md ADR-008), even after an operator
registered a working Gemini credential in Provider Management — this closes that gap the same
way sports data already worked: real adapter when an active, credentialed provider exists,
mock otherwise. Resolved per call (not once at construction) so a credential added, disabled, or
revoked after startup takes effect on the very next call, matching `SportsProviderRouter`.

A failed real call (bad/expired key, Gemini outage, network error — anything the adapter reports
as a `TextIntelligenceRequestError`) falls back to the mock adapter rather than raising: an LLM
narration failure must never break prediction generation, whose actual verdict/confidence never
touched an LLM in the first place (docs/architecture.md "Predictions must never originate from an
LLM"). Before this router existed the whole port was mock-only and could never fail this way;
adding a real path without this fallback would make the platform less reliable than it was, not
more.

The resolution step itself (looking up the provider/credential rows) gets the same treatment: if
that lookup fails at the database level — e.g. a narrower execution context that never provisioned
the admin schema — that is itself grounds to fall back to mock, not to raise. Whether a provider is
configured is auxiliary information; being unable to determine it is not a reason to break the
primary feature.

News Intelligence audit (2026-08-27) — `fallback_adapters`: additive support for a CHAIN of
further real providers, tried in order after `real_adapter`, before finally falling to
`mock_adapter`. Built after a live-observed Gemini quota exhaustion during this session's own
verification run (36 of 37 real calls returning HTTP 429) made clear that "one real provider, then
straight to mock" wastes a second real, working provider's capacity whenever the first one is
throttled. Empty by default (`()`) — every existing caller/test that only ever passed
`real_adapter` is completely unaffected; a market like `real_adapter=GeminiAdapter(...),
fallback_adapters=(ClaudeAdapter(...),)` only changes behavior for callers that opt in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from modules.admin.application.provider_management_service import ProviderManagementService
from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
    TextIntelligenceProviderPort,
    TextIntelligenceRequestError,
)

logger = logging.getLogger("titaniq.intelligence")


@dataclass
class TextIntelligenceRouter:
    admin_service: ProviderManagementService
    real_adapter: TextIntelligenceProviderPort
    mock_adapter: TextIntelligenceProviderPort
    provider_key: str = "gemini"
    fallback_adapters: tuple[TextIntelligenceProviderPort, ...] = field(default_factory=tuple)

    async def _is_usable(self, adapter: TextIntelligenceProviderPort) -> bool:
        try:
            provider = await self.admin_service.providers.get_by_key(adapter.provider_key)
            if provider is None or not provider.is_usable():
                return False
            credentials = await self.admin_service.usable_credentials(provider.id)
        except SQLAlchemyError:
            return False
        return bool(credentials)

    async def _usable_chain(self) -> list[TextIntelligenceProviderPort]:
        """`real_adapter` first, then `fallback_adapters` in the order given — every adapter in
        the chain re-checked per call (not cached), same "a credential change takes effect on the
        very next call" contract the single-adapter version already had."""
        chain = (self.real_adapter, *self.fallback_adapters)
        usable = []
        for adapter in chain:
            if await self._is_usable(adapter):
                usable.append(adapter)
        return usable

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        usable = await self._usable_chain()
        for adapter in usable:
            for attempt in range(2):  # one retry per adapter — a meaningful share of request
                # errors are transient (HTTP 503 "high demand", a network read timeout) and
                # succeed on a second try; retrying once here, before moving to the next provider
                # in the chain, measurably increases how often callers get a real response instead
                # of falling further down the chain, without weakening the fallback guarantee.
                try:
                    return await getattr(adapter, method)(*args, **kwargs)
                except TextIntelligenceRequestError as exc:
                    if attempt == 0:
                        continue
                    # Safe to log str(exc) here — every real adapter's own request-error subclass
                    # builds its message from the response status/body only, never the raw
                    # credential (GeminiAdapter's URL-param key is deliberately excluded from its
                    # error text; ClaudeAdapter's key never leaves its request header at all).
                    logger.warning(
                        "%s real-adapter call to '%s' failed after retry — trying next provider in the chain: %s",
                        adapter.provider_key, method, exc,
                    )
                    break  # exhausted retries for this adapter — advance to the next one, if any
        return await getattr(self.mock_adapter, method)(*args, **kwargs)

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        return await self._call("extract_events", text)

    async def summarize(self, text: str, *, max_words: int = 120) -> str:
        return await self._call("summarize", text, max_words=max_words)

    async def explain(self, context: dict) -> str:
        return await self._call("explain", context)

    async def interpret_sentiment(self, text: str) -> str:
        return await self._call("interpret_sentiment", text)

    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        return await self._call("extract_entities", text)

    async def extract_relationships(self, text: str) -> list[ExtractedRelationship]:
        return await self._call("extract_relationships", text)

    async def classify_topics(self, text: str) -> list[str]:
        return await self._call("classify_topics", text)

    async def detect_language(self, text: str) -> str:
        return await self._call("detect_language", text)

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        return await self._call("extract_key_phrases", text, limit=limit)

    async def assess_prediction_context(self, payload: dict) -> str:
        return await self._call("assess_prediction_context", payload)

    async def explain_football_prediction(self, payload: dict) -> str:
        return await self._call("explain_football_prediction", payload)
