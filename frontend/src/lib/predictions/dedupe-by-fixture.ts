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

/** The single ranked pick pool Intelligence Now + Priority Intelligence draw their lead items
 * from — dedup + confidence-descending sort, deliberately with NO confidence floor. Live bug
 * (2026-08-23): this used to apply `AI_PICK_CONFIDENCE_FLOOR` (0.65, the "AI Picks" curated-feed
 * threshold) here too, so on a day where the best published prediction sits at, say, 0.60,
 * Intelligence Now/Priority Intelligence went completely empty ("No qualifying intelligence has
 * been published yet") despite real published predictions existing — directly contradicting
 * their own copy ("surfaces the strongest currently available signal ... at least moderate
 * confidence"). Only `/app/picks` and Top Intelligence (both genuinely "our best/most confident
 * picks" surfaces) apply that floor — see `AI_PICK_CONFIDENCE_FLOOR` at the Top Intelligence call
 * site and `ai-picks-page.tsx`. */
export function rankPicks(picks: PredictionPickDto[]): PredictionPickDto[] {
  return dedupeByFixture(picks).sort((a, b) => b.confidence_composite - a.confidence_composite)
}
