"""Professional Gemini Analyst Upgrade §21 — one shared anti-fabrication check, reused by every
explanation service that lets Gemini cite `source_id` values back at TitanIQ.

`FootballExplanationService._narrate_evidence` and `ContextualReasoningService._review_from_
validated` each let Gemini attach `source_id`s to its own narration (which evidence item a claim
is about). Prompt instructions ("only cite source_ids you were given") are not enforcement — a
model can still hallucinate an id that was never supplied. This module is the code-level backstop:
strip anything Gemini returns that TitanIQ didn't actually hand it, before it ever reaches a
domain entity, persistence, or the API. Pure and dependency-free so both application services (and
any future explanation service) call the same check rather than hand-rolling their own.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable


def filter_valid_source_ids(candidate_ids: Iterable[str], valid_ids: Collection[str]) -> tuple[str, ...]:
    """Real supplied evidence ids only, in their original order, duplicates collapsed. A
    `candidate_id` not present in `valid_ids` is dropped silently — never surfaced, never logged as
    if it were real evidence, since a hallucinated id is not a failure to explain to the user, it's
    simply not evidence."""
    valid = valid_ids if isinstance(valid_ids, (set, frozenset)) else set(valid_ids)
    seen: set[str] = set()
    kept: list[str] = []
    for candidate in candidate_ids:
        if candidate in valid and candidate not in seen:
            seen.add(candidate)
            kept.append(candidate)
    return tuple(kept)
