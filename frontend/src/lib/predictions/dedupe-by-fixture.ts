import type { PredictionPickDto } from '@/lib/api/types'

/** One card per fixture — `/predictions/picks` is already sorted by confidence descending, so
 * keeping only the first occurrence per `subject_ref` keeps each fixture's single highest-
 * confidence published market and drops the rest. Shared by `/app/picks` and Mission Control's
 * "Today's Top AI Intelligence" so the two surfaces can never drift on what "one card per match"
 * means. */
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
