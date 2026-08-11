import { resolveVerdict, type TeamRef } from '@/components/infinity/evidence-explorer'

/** Thin wrapper around `resolveVerdict` (the single source of truth for turning a raw prediction
 * `value` — HOME_WIN/AWAY_WIN/DRAW/YES/NO/OVER/UNDER/positive/negative — into human-readable
 * text) for call sites that only need the string, not the team/crest. */
export function predictionValueLabel(value: string | number, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  return resolveVerdict(value, homeTeam, awayTeam).text
}
