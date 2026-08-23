/** Shared, dependency-free prediction-formatting helpers — extracted so both `prediction-
 * intelligence.tsx` and `actual-vs-predicted-card.tsx` can use them without importing each other
 * (the latter needs `PredictionFreshness`, the former needs `ActualVsPredictedCard` — a direct
 * import either way would be circular). `prediction-intelligence.tsx` re-exports these so every
 * existing external import of them keeps working unchanged. */

/** Real market-key suffixes (`football.match_winner`, `football.correct_score`) — matched by
 * `.endsWith()` so this stays sport-prefix-agnostic. */
export const MATCH_WINNER_SUFFIX = '.match_winner'
export const CORRECT_SCORE_SUFFIX = '.correct_score'

/** Same 48h staleness threshold `PredictionConsistencyGate` (backend) already uses to gate Gemini
 * narration — reused here rather than a second, arbitrary UI-only number. */
const STALE_AFTER_MS = 48 * 60 * 60 * 1000

export function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function PredictionFreshness({ generatedAt }: { generatedAt: string | null }) {
  if (!generatedAt) return null
  const stale = Date.now() - new Date(generatedAt).getTime() > STALE_AFTER_MS
  return (
    <span
      className="shrink-0 font-[var(--cd-font-tabular)] text-[11px] tabular-nums"
      style={{ color: stale ? 'var(--cd-negative)' : 'var(--cd-text-muted)' }}
    >
      {stale ? 'Prediction may be outdated · ' : 'Updated '}
      {timeAgo(generatedAt)}
    </span>
  )
}
