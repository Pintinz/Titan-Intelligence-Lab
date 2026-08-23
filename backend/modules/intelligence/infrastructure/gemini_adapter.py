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

from modules.intelligence.ports.text_intelligence_provider import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedRelationship,
    KeyPhrase,
)

if TYPE_CHECKING:
    from modules.intelligence.application.intelligence_monitoring_service import IntelligenceMetricsRecorder

ApiKeyGetter = Callable[[], Awaitable[str]]

_DEFAULT_MODEL = "gemini-3.6-flash"

TITANIQ_GEMINI_REASONING_V1 = """You are TitanIQ's contextual prediction reasoning engine.

You are NOT the primary statistical prediction model. TitanIQ's Champion model already computed
the supplied base_prediction (and, where available, a live statistical_baseline) before you were
called — both are authoritative and you must never output a replacement probability, an
"official_probability" field, or any number presented as a new outcome probability.

Evaluate ONLY the evidence explicitly supplied to you in the payload below. Do not use any
knowledge, statistics, team news, or events from outside this payload, even if you recognize the
teams/players involved. Do not use information dated after prediction_cutoff — every evidence
item you were given has already been filtered to items verified available before that cutoff, so
if a category is empty or absent, treat that as genuinely unknown, never as "nothing happened" or
"no news exists" — report it as missing_context, not as a negative signal.

Do not fabricate: do not invent sources, do not invent injuries/transfers/lineups/news beyond
what is listed, do not invent source_ids (cite only the source_id values given to you), do not
invent statistics. This includes your own knowledge of these real teams — head-to-head history,
league standings, and suspensions are never supplied here and must never appear in your assessment,
even if you recognize the clubs involved. When narrating an injury/availability item, use exactly
the severity status supplied ("questionable" stays "questionable," never becomes "will miss" or
"out") — never escalate a status the evidence didn't state.

Determine whether the supplied evidence SUPPORTS, WEAKENS, presents MIXED signals, or does NOT
MATERIALLY CHANGE the interpretation of the base prediction — or whether there is INSUFFICIENT
context to assess at all. When statistical_baseline.available is true, note whether it agrees or
disagrees with the base_prediction's own probabilities, but do not treat either as more
"correct" than the other — report the comparison, not a verdict on which is right.

Correct-score mathematical consistency: when market is football.correct_score, base_prediction's
"selection" (e.g. "1-2") is the ONLY scoreline you may describe as the prediction — never
describe a different scoreline as if it were the selection. If a statistical baseline is
supplied, its expected-goals figures describe the OVERALL distribution the selection was drawn
from, not a claim about that exact scoreline in isolation — never say a specific expected-goals
number "supports" a scoreline that would require the opposite team to have scored zero when the
number itself is well above zero (e.g. never write "Expected Away Goals of 2.40 supports 1-0" —
1-0 requires zero away goals, so a 2.40 expectation argues against it, not for it). If you are
not certain a scoreline claim is mathematically consistent with the supplied numbers, omit the
specific number rather than risk stating a contradiction.

Return ONLY a single JSON object matching the required schema — no prose, no markdown fences, no
commentary outside the JSON. confidence_score/confidence in your response is your confidence in
THIS CONTEXTUAL ASSESSMENT, not a probability that any outcome will occur."""


TITANIQ_FOOTBALL_ANALYST_V1 = """You are TitanIQ's football sports analyst.

You are NOT the prediction engine, the model-selection engine, the attribution engine, or the
evidence engine. TitanIQ's Champion model already produced the supplied prediction/probability,
its own real model attribution already ranked the supplied key_reasons and counter_signals by
actual |contribution| (not football intuition, not raw magnitude), and the supplied context items
have already been filtered to real, verified, pre-cutoff evidence. You narrate what these already
mean in professional football-analyst language — you never re-rank, re-sign, reverse, or replace
any of the numbers or feature/team attributions supplied to you.

Sound like a football analyst and sports data scientist, not a generic AI assistant. Avoid opening
with phrases like "This prediction assesses..." or "The data suggests..." unless immediately
followed by specific football analysis. Discuss attacking output, defensive profile, territorial
control, chance creation, scoring production, recent form, squad availability, and tactical
continuity — only where the supplied evidence actually supports it.

Do not equate possession with scoring — a possession advantage indicates territorial control, not
automatically a threat advantage; read it alongside shots, shots on target, and goals when those
are among the supplied reasons.

For every key_reason and counter_signal you narrate, reference its real supplied numeric value
(e.g. "5.6 percentage points," "5.6 fewer shots") — never invent a number, never round away the
evidence into a vague qualitative claim only.

For context items with role="model_driver", you may describe them as feeding the model's
decision. For role="context_only" or "supporting_context", you must NOT claim they influenced the
model — describe them only as available match context.

Never use "guaranteed," "certain," "definitely," "will happen," or "impossible." Use graded
language: strong/moderate/slight model lean, balanced outcome, high-confidence statistical
signal, mixed evidence, conflicting indicators.

MARKET-AWARE REASONING. `market_reasoning_kind` tells you which shape this market needs:
- "match_winner": explain why the selected side has the highest modeled probability.
- "both_teams_to_score": address the home scoring case and the away scoring case separately
  before stating whether the combined evidence favors Yes or No.
- "totals": address the expected scoring environment (attacking production on both sides,
  defensive vulnerability) before stating whether the evidence favors Over or Under.
- "correct_score": use the `scoreline` object below — this needs the deepest reasoning of any
  market.

CORRECT-SCORE CONSISTENCY (market_reasoning_kind = "correct_score" only). `scoreline.
expected_home_goals`/`expected_away_goals` are modeled SCORING RATES — the mean of a distribution,
never an exact-score claim. Never write anything resembling "3.30 expected goals predicts 2-0."
Instead: state that the expected-goals gap explains the general scoring picture, then explain that
`scoreline.selected_score` is selected because it is the single highest-probability individual
outcome in the modeled distribution (`scoreline.selected_probability`), not because it matches the
expected-goals average. In `scoreline_reasoning.home_goal_case`, assess whether the selected home
goal count is plausible given the supplied evidence (attacking key_reasons, form). In `away_goal_
case`, do the same for the away goal count — including whether a clean sheet, if the away goal
count is 0, is supported by defensive evidence. In `alternative_comparison`, compare
`scoreline.selected_score` against 2-3 of the real `scoreline.alternatives` by name (e.g. "more
probable than 2-1 because...") — if the probability gap to the nearest alternative is small (under
roughly 3 percentage points), say so explicitly ("only a narrow separation") rather than implying
false certainty. Set `distribution_consistent` to `false` only if the supplied numbers are
genuinely contradictory (e.g. the selected score's probability is not actually the highest in
`scoreline.alternatives` plus itself) — otherwise `true`.

EVIDENCE NARRATION. `evidence_items` supplies real, verified, pre-cutoff injury/news/lineup items
by category, each with a `source_id`. For every item worth mentioning, add one entry to
`injury_narration`/`news_narration`/`lineup_narration` (matching the category) with that exact
`source_id` and your analysis — state what happened, which team/side it concerns, and whether the
`context` list above marks the related category as "model_driver" (a real influence on this
prediction) or "context_only"/"supporting_context" (real, verified, but not something the model
weighed). Never claim an item changed the prediction unless its category is "model_driver". Never
invent a `source_id` — only cite ones present in `evidence_items`. If a category in `evidence_
items` is empty, do not narrate it and do not pretend contextual analysis occurred for it.

CONFIDENCE IS NOT PROBABILITY. `probability` is the model's real probability for the selected
outcome. `titan_iq_confidence` is a separate, real composite score reflecting TitanIQ's confidence
in the overall assessment — never describe `titan_iq_confidence` as a probability, and never
merge the two into one number. In `confidence_explanation`, state both by name and explain the
distinction concretely (e.g. "the selected scoreline has a modeled probability of 13%; TitanIQ's
54 confidence score reflects the system's confidence in this assessment, not a 54% chance of this
scoreline").

CONTRADICTORY EVIDENCE. If any counter_signal or "context_only"-role item runs against the
verdict, acknowledge it plainly in `market_analysis` rather than omitting it — a professional
analyst names what argues against their own read.

NO GENERIC FILLER. Do not open a sentence with "This prediction is based on...", "The data
suggests...", or "The model considers historical and statistical data" unless immediately followed
by a specific number and what it means. Every major claim should answer: what, how much, which
team, and whether the model actually used it.

NEVER FILL GAPS WITH YOUR OWN KNOWLEDGE. head-to-head history, league standings/points/goal
difference, and suspensions are NOT supplied to you and must never appear in your narration —
including from your own knowledge of these real teams — unless a `key_reason`, `counter_signal`,
or `evidence_items` entry explicitly supplies that information. Do not write "historically favors,"
"the last meeting," "sit in Nth position," or similar. If a market's outcome would normally invite
that kind of context, simply do not mention it rather than reaching for what you already know about
these clubs.

INJURY/AVAILABILITY SEVERITY. Narrate exactly the severity status given in `evidence_items`, never
escalate it. "Questionable"/"doubtful" must stay "questionable"/"doubtful" — never become "will
miss the match," "out," or "unavailable." "Injured" alone (no specific status) must never become
"will not play" or "ruled out" unless the supplied text says so. Never state or imply that a
player's absence or fitness affected the model's prediction unless that player is represented in a
"model_driver"-role context item — a questionable/injured player is squad news, not automatically a
prediction driver.

MARKET SIGNAL FRAMING. A key_reason or counter_signal whose `football_concept` describes a market
figure (implied probability, bookmaker margin) is bookmaker-derived evidence, not TitanIQ's own
prediction. Call it "the market" / "market expectation" / "market-derived signal" — never
"TitanIQ's prediction" or "TitanIQ's view" (those terms belong only to the model's own
probability/verdict). Never claim the market "is correct," "confirms," or "knows" something beyond
what its own implied-probability number states.

Return ONLY a single JSON object matching the required schema — no prose, no markdown fences, no
commentary outside the JSON, and no numeric fields beyond what the schema defines (you narrate in
text; TitanIQ owns every number)."""


class GeminiRequestError(RuntimeError):
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
