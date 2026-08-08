"""Deterministic mock for TextIntelligenceProviderPort — lets every consumer (news pipeline,
explainability, recommendations) be built and tested without a Gemini API key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
)

_STOPWORDS = frozenset(
    "the a an of in on for to and or with at by from is was were are be been has have had "
    "his her their its it he she they club team match season this that as after before "
    "will win won lost".split()
)


def _humanize_feature_key(key: str) -> str:
    """Turns an internal feature key like "football.fixture.form_shots_on_target_diff_last5"
    into "Form Shots On Target Diff (last 5)" — the explanation text is user-facing narration,
    never a place to leak namespaced backend feature identifiers (mirrors the frontend's own
    humanizeFactorKey in evidence-explorer.tsx)."""
    last_segment = key.rsplit(".", 1)[-1]
    spaced = re.sub(r"_last(\d+)", r" (last \1)", last_segment, flags=re.IGNORECASE)
    spaced = spaced.replace("_", " ")
    return re.sub(r"\b\w", lambda m: m.group().upper(), spaced)


@dataclass
class MockGeminiAdapter:
    provider_key: str = "gemini"

    async def extract_events(self, text: str) -> list[ExtractedEvent]:
        """Keyword heuristic covering every `NewsEventType` category (Milestone 8 "EVENT
        EXTRACTION") — deterministic, no real inference, same posture as `extract_topics`'s
        keyword table."""
        lowered = text.lower()
        event_rules: tuple[tuple[str, tuple[str, ...], tuple[str, ...], float], ...] = (
            ("injury", ("injur",), ("mock_player",), 0.7),
            ("recovery", ("recovered", "returns to training", "back in training"), ("mock_player",), 0.6),
            ("transfer", ("transfer", "sign"), ("mock_player", "mock_team"), 0.6),
            ("suspension", ("suspend", "banned", "red card"), ("mock_player",), 0.65),
            ("manager_change", ("manager", "head coach", "sacked", "appointed"), ("mock_coach", "mock_team"), 0.6),
            ("formation_change", ("formation",), ("mock_team",), 0.55),
            ("tactical_change", ("tactic",), ("mock_team",), 0.55),
            ("training_update", ("training session", "training update"), ("mock_team",), 0.5),
            ("weather_report", ("weather", "storm", "heavy rain"), ("mock_venue",), 0.5),
            ("travel_delay", ("travel delay", "flight delay", "delayed travel"), ("mock_team",), 0.5),
            ("stadium_change", ("stadium change", "venue change", "relocated to"), ("mock_venue",), 0.55),
            ("match_postponement", ("postponed", "postponement"), ("mock_match",), 0.65),
            ("player_availability", ("doubtful", "available for selection", "fit to play"), ("mock_player",), 0.6),
            ("lineup_expectation", ("expected lineup", "starting xi", "expected to start"), ("mock_player",), 0.55),
        )
        events: list[ExtractedEvent] = []
        for event_type, keywords, entities, confidence in event_rules:
            if any(keyword in lowered for keyword in keywords):
                events.append(
                    ExtractedEvent(
                        event_type=event_type,
                        summary=f"Mock-extracted {event_type} event from source text.",
                        entities=entities,
                        confidence=confidence,
                    )
                )
        return events

    async def summarize(self, text: str, *, max_words: int = 120) -> str:
        words = text.split()
        return " ".join(words[:max_words]) + ("..." if len(words) > max_words else "")

    async def explain(self, context: dict) -> str:
        # Deterministic fallback for when the real Gemini adapter is unavailable — worded as a
        # plain statement of the same real, structured evidence the confidence-drivers checklist
        # already shows (never a fabricated stat), not labeled as a stand-in: TitanIQ's product
        # constitution requires never exposing backend implementation details to end users, the
        # same reason Expected Lineups shows a plain waiting message rather than an internal gap.
        #
        # Two more real, already-computed signals differentiate this sentence per fixture beyond
        # the top feature names alone: the market's actual projected probability, and a genuine
        # contradicting factor when the ranked contributions include one — both read straight
        # from `context`, never invented. Magnitude/strength language ("strongly", "moderately")
        # is deliberately NOT used: this adapter has no way to know a given predictor's own
        # contribution-value scale, and guessing would be exactly the kind of fabricated stat
        # this fallback exists to avoid.
        top_features = context.get("feature_importance", [])
        if not top_features:
            return "This verdict is grounded in the match's available data — no single factor dominates it."

        names = ", ".join(_humanize_feature_key(str(f.get("feature_key", "?"))) for f in top_features[:3])
        sentence = f"This verdict is driven mainly by {names}, based on the match's real historical and statistical data."

        probability = context.get("probability")
        if isinstance(probability, (int, float)):
            sentence += f" Projected probability: {probability * 100:.0f}%."

        contradicting = next(
            (f for f in top_features if isinstance(f.get("importance"), (int, float)) and f["importance"] < 0), None
        )
        if contradicting:
            opposing_name = _humanize_feature_key(str(contradicting.get("feature_key", "?")))
            sentence += f" {opposing_name} pulls the other way but isn't enough to change the call."

        return sentence

    async def interpret_sentiment(self, text: str) -> str:
        lowered = text.lower()
        positive = sum(word in lowered for word in ("win", "great", "strong", "confident"))
        negative = sum(word in lowered for word in ("loss", "injury", "weak", "doubt"))
        if positive > negative:
            return "positive"
        if negative > positive:
            return "negative"
        return "neutral"

    async def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Title-Case span heuristic: 1-3 consecutive capitalized words, deduped in order of
        first appearance. `entity_type` is inferred from a nearby keyword; "unknown" otherwise —
        real disambiguation against the Knowledge Graph happens in `EntityExtractionService`,
        not here."""
        spans = re.findall(r"\b[A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*){0,2}\b", text)
        lowered = text.lower()
        seen: dict[str, ExtractedEntity] = {}
        for span in spans:
            if span in seen or span.split()[0].lower() in _STOPWORDS:
                continue
            entity_type = "unknown"
            if any(k in lowered for k in ("fc", "club", "united", "city")):
                entity_type = "team"
            elif any(k in lowered for k in ("manager", "coach")):
                entity_type = "coach"
            elif any(k in lowered for k in ("stadium", "arena", "park")):
                entity_type = "venue"
            seen[span] = ExtractedEntity(text=span, entity_type=entity_type, confidence=0.6)
        return list(seen.values())

    async def extract_relationships(self, text: str) -> list[ExtractedRelationship]:
        """Keyword-bridged pattern match: "<Entity> <relation phrase> <Entity>", scanning known
        relation phrases mirroring the Knowledge Graph's `EdgeType` vocabulary."""
        relation_phrases = {
            "transferred to": "transferred_to",
            "signed by": "signed_by",
            "coached by": "coached_by",
            "injured in": "injured_in",
        }
        relationships: list[ExtractedRelationship] = []
        for phrase, relation in relation_phrases.items():
            pattern = re.compile(
                r"([A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*){0,2})\s+" + re.escape(phrase) +
                r"\s+([A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*){0,2})",
            )
            for match in pattern.finditer(text):
                relationships.append(
                    ExtractedRelationship(
                        subject=match.group(1), relation=relation, obj=match.group(2), confidence=0.6
                    )
                )
        return relationships

    async def classify_topics(self, text: str) -> list[str]:
        lowered = text.lower()
        topic_keywords = {
            "injury": ("injur", "recover"),
            "transfer": ("transfer", "sign"),
            "suspension": ("suspen", "banned", "red card"),
            "manager_change": ("manager", "sack", "appointed"),
            "tactics": ("formation", "tactic"),
            "match_result": ("win", "loss", "draw", "score"),
        }
        return [topic for topic, keywords in topic_keywords.items() if any(k in lowered for k in keywords)]

    async def detect_language(self, text: str) -> str:
        lowered = f" {text.lower()} "
        if any(f" {w} " in lowered for w in ("el", "la", "de", "los", "que")):
            return "es"
        if any(f" {w} " in lowered for w in ("le", "la", "et", "les", "des")):
            return "fr"
        return "en"

    async def extract_key_phrases(self, text: str, *, limit: int = 5) -> list[KeyPhrase]:
        words = re.findall(r"[a-zA-Z]+", text.lower())
        counts: dict[str, int] = {}
        for word in words:
            if word in _STOPWORDS or len(word) < 3:
                continue
            counts[word] = counts.get(word, 0) + 1
        if not counts:
            return []
        total = sum(counts.values())
        ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
        return [KeyPhrase(phrase=word, score=count / total) for word, count in ranked[:limit]]
