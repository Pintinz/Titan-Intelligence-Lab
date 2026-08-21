"""Sports-Analyst Explainability — strict schema validation of Gemini's raw JSON output.

Same posture as `gemini_reasoning_schema.py`: `model_config = ConfigDict(extra="forbid")` on
every nested model, so a hallucinated extra key fails validation outright. Gemini supplies only
narration (`analysis` strings) — every numeric field it could use to overwrite a verified
attribution value is deliberately absent from this schema; `FootballExplanationService` fills
`feature`/`football_concept`/`team`/`direction`/`contribution` from the real attribution result
before ever building the payload, and never lets Gemini's response overwrite them (§33 —
Gemini must never invent statistics, reverse feature direction, or reverse team attribution).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeyReasonNarrationSchema(_Strict):
    rank: int = Field(ge=1, le=5)
    analysis: str


class CounterSignalNarrationSchema(_Strict):
    rank: int = Field(ge=1)
    analysis: str


class EvidenceNarrationSchema(_Strict):
    """Gemini's narration of one real supplied `EvidenceItem`, cited by `source_id` — never a
    freestanding claim. `FootballExplanationService` drops any `source_id` that doesn't match an
    item it actually supplied (spec §13: Gemini may summarize evidence, never invent it)."""

    source_id: str
    analysis: str


class ScorelineReasoningSchema(_Strict):
    """Correct-Score-only (spec §2/§3/§4) — Gemini supplies only the four prose fields; every
    number (`selected_score`, probabilities, expected goals, alternatives) is already fixed by
    `FootballExplanationService` from the real distribution before Gemini ever sees it, so there
    is nothing here for Gemini to get numerically wrong, only prose to get right."""

    home_goal_case: str
    away_goal_case: str
    alternative_comparison: str
    distribution_consistent: bool


class FootballExplanationSchema(_Strict):
    """The exact top-level JSON shape `TITANIQ_FOOTBALL_ANALYST_V1` instructs Gemini to return —
    narration keyed by rank/source_id, matched back to the real `KeyReason`/`CounterSignal`/
    `EvidenceItem`/scoreline data `FootballExplanationService` already built, never a free-form
    re-statement of the numbers."""

    verdict: str
    key_reason_narration: tuple[KeyReasonNarrationSchema, ...] = Field(default=(), max_length=5)
    counter_signal_narration: tuple[CounterSignalNarrationSchema, ...] = Field(default=(), max_length=5)
    match_profile: str
    confidence_explanation: str
    bottom_line: str
    # Sports-Analyst Explainability Upgrade additions — every one optional/defaulted so a
    # response that only ever produced the six fields above (a pinned older prompt version, a
    # narrower market) still validates.
    market_analysis: str = ""
    scoreline_reasoning: ScorelineReasoningSchema | None = None
    injury_narration: tuple[EvidenceNarrationSchema, ...] = Field(default=())
    news_narration: tuple[EvidenceNarrationSchema, ...] = Field(default=())
    lineup_narration: tuple[EvidenceNarrationSchema, ...] = Field(default=())
    context_quality: str = ""
