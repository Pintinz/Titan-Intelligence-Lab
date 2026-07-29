"""Sentiment Engine (Milestone 8 "SENTIMENT ENGINE": "Support: Positive, Negative, Neutral,
Mixed, Momentum, Confidence, Target entity. Sentiment shall remain an auxiliary feature
only.").

`TextIntelligenceProviderPort.interpret_sentiment` (Milestone 3) returns one label per call —
no Mixed classification, no confidence. This engine derives both without changing that port:
splitting the input into sentences and interpreting each one surfaces disagreement (Mixed) and
yields a real confidence figure (the majority label's agreement ratio across sentences), rather
than inventing an unearned single number from one LLM call. Momentum compares this reading
against the target entity's most recent prior `SentimentResult` — the signed change in a
[-1, +1] sentiment score, not an absolute value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from modules.intelligence.domain.entities import SentimentResult
from modules.intelligence.domain.value_objects import SentimentLabel, SentimentResultId
from modules.intelligence.ports.repositories import SentimentResultRepositoryPort
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort

_LABEL_SCORE = {
    SentimentLabel.POSITIVE: 1.0,
    SentimentLabel.NEUTRAL: 0.0,
    SentimentLabel.MIXED: 0.0,
    SentimentLabel.NEGATIVE: -1.0,
}

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SentimentService:
    text_intelligence: TextIntelligenceProviderPort
    results: SentimentResultRepositoryPort

    async def analyze(
        self, text: str, target_entity_ref: str, target_entity_type: str, source_ref: str, now: datetime
    ) -> SentimentResult:
        sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s] or [text]
        raw_labels = [await self.text_intelligence.interpret_sentiment(s) for s in sentences]
        label, confidence = self._aggregate(raw_labels)

        previous = await self.results.list_for_entity(target_entity_ref, limit=1)
        previous_score = _LABEL_SCORE[previous[0].label] if previous else 0.0
        momentum = _LABEL_SCORE[label] - previous_score

        result = SentimentResult(
            id=SentimentResultId(uuid4()),
            target_entity_ref=target_entity_ref,
            target_entity_type=target_entity_type,
            label=label,
            momentum=momentum,
            confidence=confidence,
            source_ref=source_ref,
            computed_at=now,
        )
        return await self.results.record(result)

    def _aggregate(self, raw_labels: list[str]) -> tuple[SentimentLabel, float]:
        counts: dict[SentimentLabel, int] = {}
        for raw in raw_labels:
            try:
                label = SentimentLabel(raw)
            except ValueError:
                label = SentimentLabel.NEUTRAL
            counts[label] = counts.get(label, 0) + 1

        total = len(raw_labels)
        positive_count = counts.get(SentimentLabel.POSITIVE, 0)
        negative_count = counts.get(SentimentLabel.NEGATIVE, 0)
        if positive_count and negative_count:
            # genuine disagreement across sentences — confidence reflects how polarized (not
            # neutral/undecided) the disagreement is, since that's what makes it "mixed" rather
            # than just noisy.
            return SentimentLabel.MIXED, (positive_count + negative_count) / total

        majority = max(counts, key=counts.get)
        return majority, counts[majority] / total
