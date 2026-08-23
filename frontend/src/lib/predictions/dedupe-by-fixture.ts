import { AI_PICK_CONFIDENCE_FLOOR } from '@/components/command-deck/ai-picks/ai-pick-card'
import type { PredictionPickDto } from '@/lib/api/types'

/** One card per fixture — `/predictions/picks` is already sorted by confidence descending, so
 * keeping only the first occurrence per `subject_ref` keeps each fixture's single highest-
 * confidence published market and drops the rest. Shared by `/app/picks` and Mission Control's
 * Intelligence Now / Priority Intelligence / Top Intelligence so no surface can drift on what "one
 * card per match" means. */
export function dedupeByFixture(picks: PredictionPickDto[]): PredictionPickDto[] {
  const seen = new Set<string>()
  const deduped: PredictionPickDto[] = []
  for (const pick of picks) {
    if (seen.has(pick.subject_ref)) continue
    seen.add(pick.subject_ref)
    deduped.push(pick)
  }
  return deduped
}

/** The single ranked pick pool Mission Control cascades across three consumers with zero overlap
 * (Intelligence Now takes rank 0, Priority Intelligence ranks 1-3, Top Intelligence ranks 4+) —
 * one shared ranking so the same match can never appear twice on the page. Same dedup + confidence
 * floor `/app/picks` already applies, extracted here so all four call sites can't drift. */
export function rankPicks(picks: PredictionPickDto[]): PredictionPickDto[] {
  return dedupeByFixture(picks)
    .filter((pick) => pick.confidence_composite >= AI_PICK_CONFIDENCE_FLOOR)
    .sort((a, b) => b.confidence_composite - a.confidence_composite)
}
