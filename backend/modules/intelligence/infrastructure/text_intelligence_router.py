"""TextIntelligenceRouter — the real/mock resolution `SportsProviderRouter` already does for
sports data, applied to the text-intelligence port. `get_text_intelligence_provider()` used to
hardcode `MockGeminiAdapter()` permanently (docs/decisions.md ADR-008), even after an operator
registered a working Gemini credential in Provider Management — this closes that gap the same
way sports data already worked: real adapter when an active, credentialed provider exists,
mock otherwise. Resolved per call (not once at construction) so a credential added, disabled, or
revoked after startup takes effect on the very next call, matching `SportsProviderRouter`.

A failed real call (bad/expired key, Gemini outage, network error — anything the adapter reports
as `GeminiRequestError`) falls back to the mock adapter rather than raising: an LLM narration
failure must never break prediction generation, whose actual verdict/confidence never touched
Gemini in the first place (docs/architecture.md "Predictions must never originate from an LLM").
Before this router existed the whole port was mock-only and could never fail this way; adding a
real path without this fallback would make the platform less reliable than it was, not more.

The resolution step itself (looking up the provider/credential rows) gets the same treatment: if
that lookup fails at the database level — e.g. a narrower execution context that never provisioned
the admin schema — that is itself grounds to fall back to mock, not to raise. Whether Gemini is
configured is auxiliary information; being unable to determine it is not a reason to break the
primary feature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from modules.admin.application.provider_management_service import ProviderManagementService
from modules.intelligence.infrastructure.gemini_adapter import GeminiRequestError
from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
    TextIntelligenceProviderPort,
)

logger = logging.getLogger("titaniq.intelligence")


@dataclass
class TextIntelligenceRouter:
    admin_service: ProviderManagementService
    real_adapter: TextIntelligenceProviderPort
    mock_adapter: TextIntelligenceProviderPort
    provider_key: str = "gemini"

    async def _resolve(self) -> TextIntelligenceProviderPort:
        try:
            provider = await self.admin_service.providers.get_by_key(self.real_adapter.provider_key)
            if provider is None or not provider.is_usable():
                return self.mock_adapter
            credentials = await self.admin_service.usable_credentials(provider.id)
        except SQLAlchemyError:
            return self.mock_adapter
        if not credentials:
            return self.mock_adapter
        return self.real_adapter

    async def _call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        adapter = await self._resolve()
        if adapter is self.mock_adapter:
            return await getattr(adapter, method)(*args, **kwargs)
        try:
            return await getattr(adapter, method)(*args, **kwargs)
        except GeminiRequestError as exc:
            # Safe to log str(exc) here — GeminiAdapter itself now builds GeminiRequestError's
            # message from the response status/body only, never the request URL (which carries
            # the API key as a query param), so this can never leak the credential.
            logger.warning(
                "Gemini real-adapter call to '%s' failed — falling back to the mock adapter: %s",
                method, exc,
            )
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
