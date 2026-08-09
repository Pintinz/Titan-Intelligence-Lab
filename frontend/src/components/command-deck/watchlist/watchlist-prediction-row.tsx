import { Link } from 'react-router-dom'
import { ChevronRight, Star } from 'lucide-react'
import { resolveVerdict, type TeamRef } from '@/components/infinity/evidence-explorer'

const VALUE_LABELS: Record<string, string> = {
  YES: 'Yes',
  NO: 'No',
  OVER: 'Over',
  UNDER: 'Under',
  positive: 'Yes',
  negative: 'No',
}

function valueLabel(value: string | number, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  const stringValue = String(value)
  if (stringValue in VALUE_LABELS) return VALUE_LABELS[stringValue]
  return resolveVerdict(value, homeTeam, awayTeam).text
}

/**
 * WatchlistPredictionRow — a compact intelligence-feed row, deliberately not a card: the shaped
 * brief is explicit that a followed prediction is "the intelligence signal I'm monitoring," not a
 * second rendering of the match it belongs to. Market/outcome carry the left side; probability
 * signal (confidence, evidence count) carries the right — the same market/outcome/confidence/
 * evidence fields `AiPickCard` already surfaces, at feed density instead of card density.
 */
export function WatchlistPredictionRow({
  fixtureLabel,
  marketName,
  value,
  homeTeam,
  awayTeam,
  confidence,
  evidenceCount,
  generatedAt,
  href,
  following,
  onToggleFollow,
}: {
  fixtureLabel: string | null
  marketName: string | null
  value: string | number
  homeTeam?: TeamRef
  awayTeam?: TeamRef
  confidence: number
  evidenceCount: number | null
  generatedAt: string | null
  href: string
  following: boolean
  onToggleFollow: () => void
}) {
  return (
    <div
      className="group relative flex items-center justify-between gap-4 rounded-[var(--cd-radius-md)] px-4 py-3 transition-colors duration-[var(--cd-motion-base)]"
      style={{ backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-hairline)' }}
    >
      <Link to={href} aria-label={marketName ?? 'Open prediction intelligence'} className="absolute inset-0 z-0" />
      <div className="relative z-10 min-w-0">
        {fixtureLabel && (
          <p className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            {fixtureLabel}
          </p>
        )}
        <p className="mt-0.5 truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          {marketName ?? 'Prediction'}
        </p>
        <p className="mt-0.5 truncate font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {valueLabel(value, homeTeam, awayTeam)}
        </p>
      </div>
      <div className="relative z-10 flex shrink-0 items-center gap-4">
        <div className="text-right">
          <p className="font-[var(--cd-font-tabular)] text-[15px] font-semibold tabular-nums" style={{ color: 'var(--cd-accent)' }}>
            {Math.round(confidence * 100)}%
          </p>
          <p className="mt-0.5 font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            {evidenceCount !== null ? `${evidenceCount} evidence` : 'confidence'}
          </p>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault()
            onToggleFollow()
          }}
          aria-pressed={following}
          aria-label={following ? 'Unfollow prediction' : 'Follow prediction'}
          className="pointer-events-auto rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
          style={{ color: following ? 'var(--cd-accent)' : 'var(--cd-text-muted)' }}
        >
          <Star className="size-3.5" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
        <Link
          to={href}
          className="pointer-events-auto flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
          style={{ color: 'var(--cd-text-secondary)' }}
          aria-label="Open Intelligence"
        >
          <ChevronRight className="size-3.5" aria-hidden="true" />
        </Link>
      </div>
      {generatedAt && (
        <span className="sr-only">Generated {new Date(generatedAt).toLocaleString()}</span>
      )}
    </div>
  )
}
