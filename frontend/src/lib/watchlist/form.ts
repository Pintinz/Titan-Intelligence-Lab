import type { FixtureSummaryDto } from '@/lib/api/types'

export type Outcome = 'W' | 'D' | 'L'

/** Same derivation `team-detail-page.tsx` already uses for its Recent Form grid — a completed
 * fixture's real final score, read from the given team's side. Chronological oldest-first so a
 * form strip reads left-to-right as "then -> now", matching that page's convention. Only fixtures
 * with a real recorded score contribute; anything else is silently skipped rather than guessed. */
export function deriveForm(recentFixtures: FixtureSummaryDto[], teamId: string): Outcome[] {
  return recentFixtures
    .filter((f) => f.final_state && f.final_state.home !== null && f.final_state.away !== null)
    .slice()
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
    .map((f): Outcome => {
      const isHome = f.home_team.id === teamId
      const gf = isHome ? f.final_state!.home! : f.final_state!.away!
      const ga = isHome ? f.final_state!.away! : f.final_state!.home!
      return gf > ga ? 'W' : gf < ga ? 'L' : 'D'
    })
}
