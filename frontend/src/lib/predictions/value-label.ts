import { resolveVerdict, type TeamRef } from '@/components/infinity/evidence-explorer'

/** Real backend labels every consumer of a raw prediction `value` needs to never expose as-is
 * (YES/NO/OVER/UNDER/positive/negative) — everything else (HOME_WIN/AWAY_WIN/DRAW) is already
 * human-readable via `resolveVerdict`. Single source of truth shared by AI Picks, Watchlist, and
 * Alerts so the three surfaces can never drift on how a value reads. */
const VALUE_LABELS: Record<string, string> = {
  YES: 'Yes',
  NO: 'No',
  OVER: 'Over',
  UNDER: 'Under',
  positive: 'Yes',
  negative: 'No',
}

export function predictionValueLabel(value: string | number, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  const stringValue = String(value)
  if (stringValue in VALUE_LABELS) return VALUE_LABELS[stringValue]
  return resolveVerdict(value, homeTeam, awayTeam).text
}
