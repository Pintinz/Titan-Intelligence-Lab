"""Deterministic mock for TextIntelligenceProviderPort — lets every consumer (news pipeline,
explainability, recommendations) be built and tested without a Gemini API key.
"""

from __future__ import annotations

import json
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


def _mock_market_analysis(reasoning_kind: str, market: str, prediction: str, key_reasons: list[dict], counter_signals: list[dict]) -> str:
    """Sports-Analyst Explainability Upgrade §1 — a market-aware summary sentence, deterministic
    and grounded only in the real key_reasons/counter_signals already supplied. Never invents a
    home/away split this mock has no separate evidence for; it names the reasoning shape the
    market needs and states what the supplied evidence shows either way."""
    reason_names = ", ".join(r.get("football_concept", r.get("feature", "a supplied factor")) for r in key_reasons[:2]) or "no ranked factor"
    counter_note = (
        f" {counter_signals[0].get('football_concept', counter_signals[0].get('feature', 'a counter-signal'))} runs the other way."
        if counter_signals else ""
    )
    if reasoning_kind == "both_teams_to_score":
        return f"Both sides' scoring cases hinge on {reason_names}, which together support {prediction} on {market}.{counter_note}"
    if reasoning_kind == "totals":
        return f"The expected scoring environment is shaped mainly by {reason_names}, supporting {prediction} on {market}.{counter_note}"
    if reasoning_kind == "correct_score":
        return f"The scoreline distribution is shaped mainly by {reason_names}.{counter_note}"
    return f"{market} is driven mainly by {reason_names}.{counter_note}"


def _mock_scoreline_reasoning(scoreline: dict | None) -> dict | None:
    """Correct-Score-only (§2/§3/§4) — every comparison here reads real numbers already present
    in `scoreline` (selected/alternative probabilities, expected goals); the mock never guesses at
    football causation beyond "higher/lower than the nearest alternative"."""
    if not scoreline:
        return None
    selected_score = scoreline.get("selected_score", "?-?")
    selected_probability = scoreline.get("selected_probability", 0.0)
    home_goals, away_goals = scoreline.get("expected_home_goals"), scoreline.get("expected_away_goals")
    alternatives = scoreline.get("alternatives") or []
    home_case = (
        f"Home side's modeled scoring rate is {home_goals:.2f} — the {selected_score.split('-')[0]} goal outcome "
        f"sits within the modeled distribution around that rate, not as an exact prediction of it."
        if isinstance(home_goals, (int, float)) else
        "No modeled home scoring rate was supplied for this fixture."
    )
    away_case = (
        f"Away side's modeled scoring rate is {away_goals:.2f} — the {selected_score.split('-')[1]} goal outcome "
        f"sits within the modeled distribution around that rate, not as an exact prediction of it."
        if isinstance(away_goals, (int, float)) else
        "No modeled away scoring rate was supplied for this fixture."
    )
    if alternatives:
        nearest = max(alternatives, key=lambda a: a.get("probability", 0.0))
        gap = (selected_probability - nearest.get("probability", 0.0)) * 100
        margin = "only a narrow separation from" if abs(gap) < 3 else ("a clear margin over" if gap > 0 else "a lower probability than")
        comparison = (
            f"{selected_score} ({selected_probability:.1%}) has {margin} the next-most-probable scoreline "
            f"{nearest.get('score', '?-?')} ({nearest.get('probability', 0.0):.1%})."
        )
        consistent = gap >= 0
    else:
        comparison = f"{selected_score} ({selected_probability:.1%}) is the modeled distribution's leading scoreline; no real alternatives were supplied to compare against."
        consistent = True
    return {
        "home_goal_case": home_case, "away_goal_case": away_case,
        "alternative_comparison": comparison, "distribution_consistent": consistent,
    }


def _mock_evidence_narration(items: list[dict], context_summary: dict | None) -> list[dict]:
    """§5/§6/§17 — one narration entry per real supplied evidence item, citing its real
    `source_id`. `context_summary["role"]` (from `_classify_context`) decides whether this mock
    describes the item as a model driver or as available-but-not-material context — it never
    claims influence the role classification doesn't support."""
    if not items:
        return []
    role = (context_summary or {}).get("role", "context_only")
    influence = "fed into this model's prediction" if role == "model_driver" else "is verified context, not a material driver of this model's prediction"
    return [
        {"source_id": item["source_id"], "analysis": f"{item.get('summary', 'Verified item')} — this {influence}."}
        for item in items
        if item.get("source_id")
    ]


def _mock_context_quality(evidence_items: dict[str, list[dict]]) -> str:
    """§11 — an honest read of what evidence was actually available, never inflating an empty
    category into "analysis occurred"."""
    populated = {category: len(items) for category, items in evidence_items.items() if items}
    if not populated:
        return "No verified pre-cutoff injury, news, or lineup evidence was available, so contextual factors were not used as supporting evidence."
    parts = ", ".join(f"{count} {category}" for category, count in populated.items())
    return f"Verified pre-cutoff evidence available: {parts}."


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
                        # Real (if simple) rule-based classification over the real article text —
                        # worded as a plain statement like every sibling method here (summarize,
                        # interpret_sentiment, classify_topics), never self-labeled "mock": that
                        # wording was a backend implementation detail leaking into user-facing
                        # copy wherever a NewsEvent's summary is displayed (e.g. the public
                        # landing page's News Intelligence cards).
                        summary=f"A {event_type.replace('_', ' ')} event was identified in this article.",
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

    async def assess_prediction_context(self, payload: dict) -> tuple[str, str]:
        """Deterministic fallback matching `GeminiReasoningResponseSchema` exactly — grounded
        only in real counts already present in `payload` (never a sentiment judgment this mock
        has no way to make honestly). A market with zero accepted evidence items across every
        category gets `INSUFFICIENT_CONTEXT`, never a fabricated SUPPORTED/CHALLENGED verdict;
        a market with real evidence gets a plain NEUTRAL "context exists, count noted" read —
        this mock never claims impact direction it can't actually assess."""
        context = payload.get("context", {}) or {}
        counts = {category: len(items or []) for category, items in context.items()}
        total = sum(counts.values())
        missing = [category for category, count in counts.items() if count == 0]

        if total == 0:
            return json.dumps(
                {
                    "prediction_review": {
                        "status": "INSUFFICIENT_CONTEXT",
                        "overall_assessment": "No verified pre-cutoff contextual evidence was available for this fixture.",
                        "confidence": {"level": "VERY_LOW", "score": 0.1},
                    },
                    "contextual_assessment": {},
                    "supporting_factors": [],
                    "risk_factors": [],
                    "missing_context": missing,
                    "prediction_reconsideration": {
                        "direction": "INSUFFICIENT_EVIDENCE",
                        "material_change": False,
                        "reason": "No contextual evidence was supplied to assess against the base prediction.",
                    },
                    "evidence_quality": {
                        "overall": "VERY_LOW", "source_count": 0, "timestamp_valid": True,
                        "pre_event_only": True, "conflicting_information": False,
                    },
                }
            ), "mock"

        contextual_assessment = {
            category: {
                "impact": "NEUTRAL",
                "strength": "MEDIUM" if count >= 3 else "LOW",
                "score": 0.5,
                "reason": f"{count} verified pre-cutoff {category} item(s) available; no directional read without live reasoning.",
            }
            for category, count in counts.items()
            if count > 0
        }
        return json.dumps(
            {
                "prediction_review": {
                    "status": "NEUTRAL",
                    "overall_assessment": f"{total} verified pre-cutoff evidence item(s) found across {len(contextual_assessment)} category(ies); no directional judgment made.",
                    "confidence": {"level": "MEDIUM", "score": 0.5},
                },
                "contextual_assessment": contextual_assessment,
                "supporting_factors": [],
                "risk_factors": [],
                "missing_context": missing,
                "prediction_reconsideration": {
                    "direction": "NO_MATERIAL_CHANGE",
                    "material_change": False,
                    "reason": "Real evidence exists but this fallback does not perform sentiment reasoning over it.",
                },
                "evidence_quality": {
                    "overall": "MEDIUM", "source_count": total, "timestamp_valid": True,
                    "pre_event_only": True, "conflicting_information": False,
                },
            }
        ), "mock"

    async def explain_football_prediction(self, payload: dict) -> tuple[str, str]:
        """Deterministic fallback matching `FootballExplanationSchema` exactly — narrates only
        real supplied numbers (never a sentiment judgment this mock has no way to make honestly).
        No qualitative claim this mock can't actually ground: it states the feature, its real
        contribution value, and its already-computed direction, nothing more. Sports-Analyst
        Explainability Upgrade: also produces the market-aware/scoreline/evidence-narration
        fields a real Gemini call would, since this mock is what actually renders whenever the
        real adapter is unavailable (e.g. provider quota exhausted) — those callers deserve the
        same structure, not a degraded one."""
        key_reasons = payload.get("key_reasons", []) or []
        counter_signals = payload.get("counter_signals", []) or []
        prediction = payload.get("prediction", "this outcome")
        market = payload.get("market", "this market")
        reasoning_kind = payload.get("market_reasoning_kind", "generic")
        probability = payload.get("probability", 0)
        titan_confidence = payload.get("titan_iq_confidence")

        key_reason_narration = [
            {
                "rank": r.get("rank", i + 1),
                "analysis": (
                    f"{r.get('football_concept', r.get('feature', 'this factor'))} "
                    f"({'team: ' + r['team'] + ', ' if r.get('team') else ''}"
                    f"contribution {r.get('contribution', 0):+.3f}) {r.get('direction', 'supports')} "
                    f"the {prediction} lean on {market}."
                ),
            }
            for i, r in enumerate(key_reasons)
        ]
        counter_signal_narration = [
            {
                "rank": i + 1,
                "analysis": (
                    f"{c.get('football_concept', c.get('feature', 'this factor'))} "
                    f"(contribution {c.get('contribution', 0):+.3f}) pushes against the {prediction} lean."
                ),
            }
            for i, c in enumerate(counter_signals)
        ]

        if key_reasons:
            top = key_reasons[0]
            verdict = f"TitanIQ leans toward {prediction} on {market}, primarily on {top.get('football_concept', top.get('feature', 'the leading factor'))}."
        else:
            verdict = f"TitanIQ's {prediction} lean on {market} is not backed by a ranked attribution in this fallback."

        market_analysis = _mock_market_analysis(reasoning_kind, market, prediction, key_reasons, counter_signals)
        scoreline_reasoning = _mock_scoreline_reasoning(payload.get("scoreline"))
        evidence_items = payload.get("evidence_items", {}) or {}
        context_by_type = {c.get("type"): c for c in (payload.get("context") or [])}
        injury_narration = _mock_evidence_narration(evidence_items.get("injuries", []), context_by_type.get("injuries"))
        news_narration = _mock_evidence_narration(evidence_items.get("news", []), context_by_type.get("news"))
        lineup_narration = _mock_evidence_narration(evidence_items.get("lineups", []), context_by_type.get("lineups"))
        context_quality = _mock_context_quality(evidence_items)

        if isinstance(titan_confidence, (int, float)):
            confidence_explanation = (
                f"The selected {prediction} outcome has a modeled probability of {probability:.0%}. "
                f"TitanIQ's {titan_confidence:.0%} confidence score reflects the system's confidence in this "
                f"overall assessment — not a {titan_confidence:.0%} probability of {prediction}."
            )
        else:
            confidence_explanation = f"Published probability {probability:.0%} for {prediction}."

        response = {
            "verdict": verdict,
            "key_reason_narration": key_reason_narration,
            "counter_signal_narration": counter_signal_narration,
            "match_profile": f"{len(key_reasons)} model-attributed factor(s) and {len(counter_signals)} counter-signal(s) considered.",
            "confidence_explanation": confidence_explanation,
            "bottom_line": verdict,
            "market_analysis": market_analysis,
            "injury_narration": injury_narration,
            "news_narration": news_narration,
            "lineup_narration": lineup_narration,
            "context_quality": context_quality,
        }
        if scoreline_reasoning is not None:
            response["scoreline_reasoning"] = scoreline_reasoning
        return json.dumps(response), "mock"

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
