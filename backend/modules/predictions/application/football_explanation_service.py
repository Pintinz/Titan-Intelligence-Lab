"""Sports-Analyst Explainability — orchestrator (Phase 3, Workstream B).

Wires `ModelAttributionService` (real per-instance attribution) + `football_semantic_mapping`
(feature -> football concept) + `LiveEvidenceGatherer` (cutoff-safe context, reused unchanged) +
`GeminiAdapter.explain_football_prediction` (via `TextIntelligenceRouter`, real/mock resolution
reused unchanged) + `FootballExplanationSchema` (strict validation) into one call: `explain()`.

The authoritative chain this method enforces (§34): PREDICTION (already generated, supplied in)
-> ATTRIBUTION (real, computed here) -> EVIDENCE (cutoff-safe, gathered here) -> EXPLANATION
(Gemini narrates only what TitanIQ already computed). Gemini never receives raw feature values to
rank itself — it receives an already-ranked `key_reasons`/`counter_signals` list and is asked only
to narrate `analysis` text per rank (see `football_explanation_schema.py`'s own docstring for why
this is a stronger anti-hallucination design than mirroring the full contract literally).

Every failure mode (no champion, unfitted model, multiclass without a heuristic fallback, Gemini
unavailable, malformed JSON, schema validation failure) degrades to a `FootballExplanation` with
`status=UNAVAILABLE` — this method never raises out to its caller, matching the absolute rule that
an explanation failure must never break the underlying quantitative prediction.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime

from pydantic import ValidationError

from modules.ingestion.ports.cache import SyncCachePort
from modules.intelligence.ports.text_intelligence_provider import TextIntelligenceProviderPort
from modules.predictions.application.live_evidence_gatherer import LiveEvidenceGatherer
from modules.predictions.application.model_attribution_service import (
    AttributedFeature,
    BackgroundSampleRequiredError,
    ModelAttributionService,
    UnsupportedForMulticlassError,
)
from modules.predictions.application.dataset_builder_service import DatasetBuilder
from modules.predictions.application.prediction_consistency_gate import PredictionConsistencyGate
from modules.predictions.domain import football_semantic_mapping as mapping
from modules.predictions.domain.entities import MarketDefinition, ModelDefinition, Prediction
from modules.predictions.domain.evidence_source_validation import filter_valid_source_ids
from modules.predictions.domain.football_explanation import (
    AttributionMethod,
    ContextItem,
    ContextRole,
    CounterSignal,
    ExplanationStatus,
    FootballExplanation,
    KeyReason,
    NarratedEvidence,
    ScorelineAlternative,
    ScorelineReasoning,
)
from modules.predictions.domain.value_objects import TargetType
from modules.predictions.infrastructure.football_explanation_schema import FootballExplanationSchema
from modules.predictions.infrastructure.ml.model_loader import ModelLoaderService
from modules.predictions.ports.football_explanation_repository import FootballExplanationRepositoryPort
from modules.predictions.ports.repositories import ModelRepositoryPort

_PROMPT_VERSION = "TITANIQ_FOOTBALL_ANALYST_V1"
_MAX_KEY_REASONS = 5
_MAX_COUNTER_SIGNALS = 5
_MODEL_DRIVER_THRESHOLD = 0.01  # |contribution| below this reads as "not a material model driver"
_BACKGROUND_SAMPLE_SIZE = 20
# Real Gemini quota is genuinely scarce (the free tier caps at a handful of requests/day/model) —
# re-narrating the same already-generated prediction on every "Generate Intelligence" click or
# page revisit burns that quota for zero new information, since attribution is a deterministic
# function of the prediction's own fixed feature_snapshot. Mirrors ContextualReasoningService's
# own cache TTL/keying discipline exactly (`contextual_reasoning_service.py`) — one cache
# convention across both Gemini-calling services, not two.
_CACHE_TTL_SECONDS = 6 * 60 * 60

# Real context category -> real feature-key suffixes that could plausibly represent it — used
# only to classify role (§22), never to fabricate a feature that doesn't exist in the model.
_CONTEXT_FEATURE_HINTS: dict[str, tuple[str, ...]] = {
    "injuries": ("injured_players_count", "key_players_unavailable"),
    "transfers": ("transfer_activity",),
    "lineups": ("lineup_continuity",),
    "news": ("news_market_impact",),
}


def _unavailable(prediction: Prediction, market: MarketDefinition, now: datetime, reason: str) -> FootballExplanation:
    return FootballExplanation(
        status=ExplanationStatus.UNAVAILABLE,
        market_key=market.market_key,
        prediction_value=prediction.value,
        probability=prediction.probability,
        model_algorithm="",
        attribution_method=AttributionMethod.UNAVAILABLE,
        unavailable_reason=reason,
        subject_ref=prediction.subject_ref,
        model_id=str(prediction.model_id.value) if prediction.model_id else None,
        prompt_version=_PROMPT_VERSION,
        generated_at=now,
    )


def _split_reasons(attributed: tuple[AttributedFeature, ...], method: AttributionMethod) -> tuple[tuple[KeyReason, ...], tuple[CounterSignal, ...]]:
    supporting = [a for a in attributed if a.contribution >= 0][:_MAX_KEY_REASONS]
    opposing = [a for a in attributed if a.contribution < 0][:_MAX_COUNTER_SIGNALS]
    key_reasons = tuple(
        KeyReason(
            rank=i + 1, feature=a.feature_key, football_concept=mapping.describe(a.feature_key),
            team=mapping.team_for_feature(a.feature_key), direction="supports", contribution=a.contribution,
            evidence=f"{a.feature_key} = {a.value:.4g}",
        )
        for i, a in enumerate(supporting)
    )
    counter_signals = tuple(
        CounterSignal(
            feature=a.feature_key, football_concept=mapping.describe(a.feature_key), contribution=a.contribution,
        )
        for a in opposing
    )
    return key_reasons, counter_signals


def _classify_context(evidence, attributed_by_key: dict[str, float], feature_universe: set[str]) -> tuple[ContextItem, ...]:
    items = []
    for category, category_items in evidence.items_by_category.items():
        if not category_items:
            continue
        hints = _CONTEXT_FEATURE_HINTS.get(category, ())
        contribution = 0.0
        role = ContextRole.SUPPORTING_CONTEXT
        matched_in_model = any(h in feature_universe for h in hints)
        if matched_in_model:
            contribution = max((abs(attributed_by_key.get(h, 0.0)) for h in hints), default=0.0)
            role = ContextRole.MODEL_DRIVER if contribution >= _MODEL_DRIVER_THRESHOLD else ContextRole.CONTEXT_ONLY
        items.append(
            ContextItem(
                type=category, description=f"{len(category_items)} verified pre-cutoff {category} item(s)",
                model_contribution=contribution, role=role,
            )
        )
    return tuple(items)


_SCORE_KEY_PATTERN = re.compile(r"^(\d+)-(\d+)$")
_MAX_SCORELINE_ALTERNATIVES = 6
_MAX_EVIDENCE_ITEMS_PER_CATEGORY = 8

# Real market_key -> reasoning-kind classification (spec §1) — a closed, explicit list rather than
# a market_kind-derived guess, since MarketKind (BINARY/SPREAD/TOTAL/...) describes the predictor
# *shape*, not the football-analyst reasoning template a market needs. A market_key this dict
# doesn't name gets the generic template — never a guessed specialization.
_CORRECT_SCORE_MARKET_KEY = "football.correct_score"
_BOTH_TEAMS_TO_SCORE_MARKET_KEYS = frozenset({"football.both_teams_to_score", "football.first_half_both_teams_to_score"})
_TOTALS_MARKET_KEY_PREFIXES = ("football.total_goals_over_under", "football.home_team_total_goals", "football.away_team_total_goals", "football.first_half_goals")


def _market_reasoning_kind(market_key: str) -> str:
    if market_key == _CORRECT_SCORE_MARKET_KEY:
        return "correct_score"
    if market_key in _BOTH_TEAMS_TO_SCORE_MARKET_KEYS:
        return "both_teams_to_score"
    if market_key.startswith(_TOTALS_MARKET_KEY_PREFIXES):
        return "totals"
    if "winner" in market_key or market_key == "football.match_result":
        return "match_winner"
    return "generic"


def _build_scoreline_reasoning_seed(prediction: Prediction) -> ScorelineReasoning | None:
    """The real, numeric half of Correct-Score reasoning (spec §2/§3/§4) — every field here comes
    straight from `probability_distribution`/`feature_snapshot`; Gemini only ever supplies the
    four prose fields on top (`_apply_scoreline_narration`). Returns `None` for any market whose
    `value` isn't a real "H-A" scoreline (every other market) or whose distribution isn't actually
    score-shaped (defends against a coincidentally score-like value on an unrelated market)."""
    match = _SCORE_KEY_PATTERN.match(str(prediction.value))
    if match is None:
        return None
    distribution = prediction.probability_distribution or {}
    # Requires a real grid (>=4 score-shaped keys, matching the frontend's own
    # `parseScoreGrid` threshold) — a 2-key distribution isn't a Correct Score market, just a
    # coincidentally score-like value on some other market (e.g. a set-score binary outcome).
    if sum(1 for k in distribution if _SCORE_KEY_PATTERN.match(k)) < 4:
        return None
    alternatives = tuple(
        ScorelineAlternative(score=k, probability=v)
        for k, v in sorted(
            ((k, v) for k, v in distribution.items() if k != prediction.value and _SCORE_KEY_PATTERN.match(k)),
            key=lambda kv: kv[1], reverse=True,
        )[:_MAX_SCORELINE_ALTERNATIVES]
    )
    home_goals = prediction.feature_snapshot.get("football.fixture.expected_home_goals")
    away_goals = prediction.feature_snapshot.get("football.fixture.expected_away_goals")
    return ScorelineReasoning(
        selected_score=str(prediction.value),
        selected_probability=distribution.get(prediction.value, prediction.probability),
        expected_home_goals=float(home_goals) if isinstance(home_goals, (int, float)) else None,
        expected_away_goals=float(away_goals) if isinstance(away_goals, (int, float)) else None,
        alternatives=alternatives,
    )


def _context_hash(evidence) -> str:
    """Identical convention to `contextual_reasoning_service._context_hash` — a stable hash of
    every real evidence item's `source_id` across all categories, so the cache key changes the
    moment genuinely new evidence appears (a new injury report, a fresh news item) rather than
    staying pinned to a stale narration indefinitely."""
    ids = sorted(item.source_id for items in evidence.items_by_category.values() for item in items)
    return hashlib.sha256(",".join(ids).encode("utf-8")).hexdigest()[:16]


def _evidence_payload(evidence, categories: tuple[str, ...]) -> dict[str, list[dict]]:
    """Real per-item evidence detail (spec §5/§6/§17) — as opposed to `_classify_context`'s
    per-category rollup used for the `context`/model-driver classification. Capped per category
    (a fixture with dozens of news items shouldn't blow out the prompt), never silently
    fabricated: a category with zero accepted items simply contributes an empty list, matched by
    `missing_context` elsewhere in the response."""
    out: dict[str, list[dict]] = {}
    for category in categories:
        items = evidence.items_by_category.get(category, ())[:_MAX_EVIDENCE_ITEMS_PER_CATEGORY]
        out[category] = [
            {
                "source_id": item.source_id, "summary": item.summary, "entity_ref": item.entity_ref,
                "published_at": item.published_at.isoformat() if item.published_at else None,
            }
            for item in items
        ]
    return out


def _apply_scoreline_narration(seed: ScorelineReasoning, narration) -> ScorelineReasoning:
    """Merges Gemini's four prose fields onto the real numeric `ScorelineReasoning` seed
    (`_build_scoreline_reasoning_seed`) — `dataclasses.replace` so every numeric field stays
    exactly what TitanIQ computed; only `*_case`/`alternative_comparison` come from `narration`."""
    return replace(
        seed, home_goal_case=narration.home_goal_case, away_goal_case=narration.away_goal_case,
        alternative_comparison=narration.alternative_comparison,
    )


def _narrate_evidence(evidence, category: str, narration_items) -> tuple[NarratedEvidence, ...]:
    """Matches Gemini's `source_id`-keyed narration back to the real supplied `EvidenceItem`s for
    one category — any `source_id` that doesn't match a real item this service actually supplied
    is silently dropped (spec §13: Gemini may summarize evidence, never invent it), never
    surfaced as if it were real. An item TitanIQ supplied but Gemini didn't narrate still appears,
    with `analysis=""`, so real evidence is never hidden for lack of narration."""
    real_items = {item.source_id: item for item in evidence.items_by_category.get(category, ())}
    valid_ids = set(filter_valid_source_ids((n.source_id for n in narration_items), real_items.keys()))
    analysis_by_source = {n.source_id: n.analysis for n in narration_items if n.source_id in valid_ids}
    return tuple(
        NarratedEvidence(
            source_id=item.source_id, category=category, summary=item.summary, entity_ref=item.entity_ref,
            source_name=item.source_name, published_at=item.published_at,
            analysis=analysis_by_source.get(item.source_id, ""),
        )
        for item in real_items.values()
    )


def _humanize_outcome_value(value: str) -> str:
    """Gemini narrates whatever `prediction` value it's handed verbatim (see this module's own
    docstring — "Gemini narrates only what TitanIQ already computed"), so a raw enum-shaped value
    like "AWAY_WIN" or "HOME_CLEAN_SHEET" would leak straight into user-facing narration text
    ("...leans toward AWAY_WIN on..."). Most markets already emit a real label by generation time
    (`outcome_label_mapper.py`'s Phase 2 table), so this only reformats the SCREAMING_SNAKE_CASE
    shape those labels (and any market Phase 2 doesn't cover) still take — "AWAY_WIN" -> "Away
    Win". A value that isn't in that shape (a correct-score "2-1", a totals threshold) passes
    through unchanged, never guessed at."""
    if re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
        return value.replace("_", " ").title()
    return value


def _build_payload(
    prediction: Prediction, market: MarketDefinition, key_reasons, counter_signals, context: tuple[ContextItem, ...],
    reasoning_kind: str, confidence_composite: float, scoreline: ScorelineReasoning | None, evidence_items: dict[str, list[dict]],
) -> dict:
    payload = {
        "sport": market.sport_code,
        "market": market.name,
        "market_reasoning_kind": reasoning_kind,
        "prediction": _humanize_outcome_value(prediction.value),
        "probability": prediction.probability,
        # TitanIQ Confidence (composite of 9 real factors) is a SEPARATE number from the model
        # probability above — spec §10's mandatory distinction. Supplied explicitly so Gemini
        # never has to guess which of the two numbers it's narrating.
        "titan_iq_confidence": confidence_composite,
        "key_reasons": [
            {
                "rank": r.rank, "feature": r.feature, "football_concept": r.football_concept, "team": r.team,
                "direction": r.direction, "contribution": r.contribution, "evidence": r.evidence,
            }
            for r in key_reasons
        ],
        "counter_signals": [
            {"feature": c.feature, "football_concept": c.football_concept, "contribution": c.contribution}
            for c in counter_signals
        ],
        "context": [
            {"type": c.type, "description": c.description, "model_contribution": c.model_contribution, "role": c.role.value}
            for c in context
        ],
        "evidence_items": evidence_items,
    }
    if scoreline is not None:
        payload["scoreline"] = {
            "selected_score": scoreline.selected_score,
            "selected_probability": scoreline.selected_probability,
            "expected_home_goals": scoreline.expected_home_goals,
            "expected_away_goals": scoreline.expected_away_goals,
            "alternatives": [{"score": a.score, "probability": a.probability} for a in scoreline.alternatives],
        }
    return payload


@dataclass
class FootballExplanationService:
    attribution: ModelAttributionService
    evidence_gatherer: LiveEvidenceGatherer
    model_loader: ModelLoaderService
    models: ModelRepositoryPort
    dataset_builder: DatasetBuilder
    text_intelligence: TextIntelligenceProviderPort
    explanations: FootballExplanationRepositoryPort | None = None
    # Pre-Gemini Prediction-Explanation Consistency Gate (spec §23) — optional, matching every
    # other port on this service, but real production wiring provides it (composition.py). When
    # set, checked as the very first step: a failed check skips Gemini (and attribution/evidence
    # work) entirely and returns (and persists) a `status=UNAVAILABLE` explanation whose
    # `unavailable_reason` names the exact failed checks.
    consistency_gate: PredictionConsistencyGate | None = None
    # Real Gemini quota is scarce — `None` (the default) preserves every existing test/caller's
    # exact prior behavior (always calls Gemini fresh); real production wiring (composition.py)
    # provides the same Redis-backed `SyncCachePort` `ContextualReasoningService` already uses.
    cache: SyncCachePort | None = None

    async def explain(
        self, prediction: Prediction, market: MarketDefinition, now: datetime, prediction_cutoff: datetime | None = None
    ) -> FootballExplanation:
        cutoff = prediction_cutoff or now

        if self.consistency_gate is not None:
            check = await self.consistency_gate.check(prediction, market, now)
            if not check.passed:
                explanation = _unavailable(prediction, market, now, check.reason)
                if self.explanations is not None:
                    try:
                        await self.explanations.record(prediction.id, explanation)
                    except Exception:  # noqa: BLE001 — persistence failure must not mask the real diagnostic
                        pass
                return explanation

        if prediction.model_id is None:
            return _unavailable(prediction, market, now, "Prediction has no associated model — cannot attribute.")
        model_def: ModelDefinition | None = await self.models.get(prediction.model_id)
        if model_def is None or not model_def.is_genuinely_trained():
            return _unavailable(prediction, market, now, "Champion model artifact unavailable.")

        try:
            adapter = await self.model_loader.load(
                model_def.id, model_def.framework, model_def.algorithm, TargetType.CLASSIFICATION, model_def.artifact_ref
            )
        except Exception:  # noqa: BLE001 — a load failure must degrade, never crash the caller
            return _unavailable(prediction, market, now, "Champion model could not be loaded.")

        attribution_method = AttributionMethod.LINEAR_COEFFICIENT
        try:
            background = await self._background_sample(market.id, now)
            attributed = self.attribution.attribute(adapter, dict(prediction.feature_snapshot), background=background)
            if attributed and attributed[0].method == "shap":
                attribution_method = AttributionMethod.SHAP
        except UnsupportedForMulticlassError:
            attributed, attribution_method = self._heuristic_fallback(prediction)
        except BackgroundSampleRequiredError:
            attributed, attribution_method = self._heuristic_fallback(prediction)
        except Exception:  # noqa: BLE001 — attribution must never crash the caller
            return _unavailable(prediction, market, now, "Model attribution failed.")

        if not attributed:
            return _unavailable(prediction, market, now, "No attributable features were available for this prediction.")

        key_reasons, counter_signals = _split_reasons(attributed, attribution_method)
        attributed_by_key = {a.feature_key: a.contribution for a in attributed}
        feature_universe = set(adapter.feature_order)

        try:
            evidence = await self.evidence_gatherer.gather(prediction.subject_ref, market.sport_code, cutoff)
        except Exception:  # noqa: BLE001 — evidence gathering must never take down the whole explanation
            from modules.predictions.application.live_evidence_gatherer import GatheredEvidence
            evidence = GatheredEvidence()
        context = _classify_context(evidence, attributed_by_key, feature_universe)

        reasoning_kind = _market_reasoning_kind(market.market_key)
        scoreline = _build_scoreline_reasoning_seed(prediction) if reasoning_kind == "correct_score" else None
        evidence_items = _evidence_payload(evidence, ("injuries", "news", "lineups"))

        payload = _build_payload(
            prediction, market, key_reasons, counter_signals, context,
            reasoning_kind, prediction.confidence.composite, scoreline, evidence_items,
        )

        # Attribution is a deterministic function of this prediction's own fixed feature_snapshot,
        # so a re-narration only needs to happen again when the real evidence actually changed —
        # keyed on the prediction's own id (one Gemini call's worth of narration belongs to
        # exactly one generated prediction) plus a hash of the real evidence supplied, exactly
        # mirroring `ContextualReasoningService`'s cache convention.
        cache_key = f"football_explanation:{prediction.id}:{_context_hash(evidence)}"
        parsed = None
        cache_hit = False
        if self.cache is not None:
            try:
                cached = await self.cache.get(cache_key)
            except Exception:  # noqa: BLE001 — a broken cache backend degrades to "always miss," never an error
                cached = None
            if cached is not None:
                try:
                    parsed = FootballExplanationSchema.model_validate(cached)
                    cache_hit = True
                except ValidationError:
                    parsed = None  # stale/incompatible cache entry — fall through to a fresh call

        raw = None
        narration_source = "cached" if cache_hit else "unavailable"
        last_error = None
        for attempt in range(2 if not cache_hit else 0):  # one retry with the validation error appended
            try:
                raw, narration_source = await self.text_intelligence.explain_football_prediction(
                    payload if attempt == 0 else {**payload, "_previous_validation_error": last_error}
                )
                parsed = FootballExplanationSchema.model_validate(json.loads(raw))
                break
            except (ValidationError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                continue
            except Exception:  # noqa: BLE001 — Gemini unavailable/timeout/network — never raise out
                break

        if parsed is not None and not cache_hit and self.cache is not None:
            try:
                await self.cache.set(cache_key, json.loads(raw), _CACHE_TTL_SECONDS)
            except Exception:  # noqa: BLE001 — a broken cache backend must never block a good result
                pass

        if parsed is None:
            explanation = FootballExplanation(
                status=ExplanationStatus.VALIDATION_FAILED if last_error else ExplanationStatus.UNAVAILABLE,
                market_key=market.market_key, prediction_value=prediction.value, probability=prediction.probability,
                model_algorithm=model_def.algorithm, attribution_method=attribution_method,
                key_reasons=key_reasons, counter_signals=counter_signals, context=context,
                unavailable_reason="Gemini did not return a schema-valid football explanation.",
                subject_ref=prediction.subject_ref, model_id=str(model_def.id.value),
                prompt_version=_PROMPT_VERSION, generated_at=now, narration_source=narration_source,
            )
        else:
            narration_by_rank = {n.rank: n.analysis for n in parsed.key_reason_narration}
            counter_narration_by_rank = {n.rank: n.analysis for n in parsed.counter_signal_narration}
            key_reasons = tuple(
                KeyReason(
                    rank=r.rank, feature=r.feature, football_concept=r.football_concept, team=r.team,
                    direction=r.direction, contribution=r.contribution, evidence=r.evidence,
                    analysis=narration_by_rank.get(r.rank, ""),
                )
                for r in key_reasons
            )
            counter_signals = tuple(
                CounterSignal(
                    feature=c.feature, football_concept=c.football_concept, contribution=c.contribution,
                    analysis=counter_narration_by_rank.get(i + 1, ""),
                )
                for i, c in enumerate(counter_signals)
            )
            scoreline_result = (
                _apply_scoreline_narration(scoreline, parsed.scoreline_reasoning)
                if scoreline is not None and parsed.scoreline_reasoning is not None
                else None
            )
            explanation = FootballExplanation(
                status=ExplanationStatus.AVAILABLE,
                market_key=market.market_key, prediction_value=prediction.value, probability=prediction.probability,
                model_algorithm=model_def.algorithm, attribution_method=attribution_method,
                key_reasons=key_reasons, counter_signals=counter_signals, context=context,
                verdict=parsed.verdict, match_profile=parsed.match_profile,
                confidence_explanation=parsed.confidence_explanation, bottom_line=parsed.bottom_line,
                market_analysis=parsed.market_analysis, scoreline_reasoning=scoreline_result,
                injury_evidence=_narrate_evidence(evidence, "injuries", parsed.injury_narration),
                news_evidence=_narrate_evidence(evidence, "news", parsed.news_narration),
                lineup_evidence=_narrate_evidence(evidence, "lineups", parsed.lineup_narration),
                context_quality=parsed.context_quality,
                subject_ref=prediction.subject_ref, model_id=str(model_def.id.value),
                prompt_version=_PROMPT_VERSION, generated_at=now, narration_source=narration_source,
            )

        if self.explanations is not None:
            try:
                await self.explanations.record(prediction.id, explanation)
            except Exception:  # noqa: BLE001 — persistence failure must not lose an otherwise-good explanation
                pass

        return explanation

    async def _background_sample(self, market_id, now: datetime) -> list[dict[str, float]]:
        dataset = await self.dataset_builder.build(market_id, now)
        samples = sorted(
            (s for s in dataset.samples if s.reference_time is not None), key=lambda s: s.reference_time
        )
        return [dict(s.features) for s in samples[-_BACKGROUND_SAMPLE_SIZE:]]

    def _heuristic_fallback(self, prediction: Prediction) -> tuple[tuple[AttributedFeature, ...], AttributionMethod]:
        """Multiclass markets (or a missing background sample) have no real per-instance
        attribution path in this v1 (see `ModelAttributionService`'s own documented limitation) —
        falls back to the existing, already-real `PredictorOutput`-derived
        `ExplanationBundle.top_positive_features`/`top_negative_features` (value * global
        importance, computed at prediction-generation time), clearly labeled
        `HEURISTIC_IMPORTANCE` rather than claimed as exact per-instance attribution."""
        bundle = prediction.explanation
        if bundle is None:
            return (), AttributionMethod.UNAVAILABLE
        attributed = [
            AttributedFeature(feature_key=key, value=prediction.feature_snapshot.get(key, 0.0), contribution=value, direction="supports" if value >= 0 else "opposes", method="heuristic_importance")
            for key, value in bundle.top_positive_features
        ] + [
            AttributedFeature(feature_key=key, value=prediction.feature_snapshot.get(key, 0.0), contribution=value, direction="supports" if value >= 0 else "opposes", method="heuristic_importance")
            for key, value in bundle.top_negative_features
        ]
        attributed.sort(key=lambda a: abs(a.contribution), reverse=True)
        return tuple(attributed), AttributionMethod.HEURISTIC_IMPORTANCE
