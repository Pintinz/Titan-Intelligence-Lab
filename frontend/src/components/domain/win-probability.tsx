import { cn } from '@/lib/cn'

interface WinProbabilityProps {
  homeTeam: string
  awayTeam: string
  homeWinProbability: number
  drawProbability?: number
  awayWinProbability: number
  className?: string
}

/**
 * Win Probability — shows match outcome distribution.
 * Three-way split (home/draw/away) or two-way split depending on sport.
 * Communicates likelihood at a glance with color-coded bars.
 */
export function WinProbability({
  homeTeam,
  awayTeam,
  homeWinProbability,
  drawProbability,
  awayWinProbability,
  className,
}: WinProbabilityProps) {
  const total = homeWinProbability + (drawProbability || 0) + awayWinProbability

  const homePercent = (homeWinProbability / total) * 100
  const drawPercent = drawProbability ? (drawProbability / total) * 100 : 0
  const awayPercent = (awayWinProbability / total) * 100

  return (
    <div className={cn('space-y-3', className)}>
      {/* Bars */}
      <div className="flex h-8 gap-1 overflow-hidden rounded-lg border border-border-subtle bg-bg-secondary p-0.5">
        {/* Home team bar */}
        <div
          className="rounded bg-gradient-to-r from-accent-primary to-accent-primary/70 transition-all duration-300 flex items-center justify-center"
          style={{ width: `${homePercent}%`, minWidth: homePercent > 15 ? 'auto' : 0 }}
        >
          {homePercent > 15 && (
            <span className="text-xs font-semibold text-text-inverse tabular-nums">
              {homePercent.toFixed(0)}%
            </span>
          )}
        </div>

        {/* Draw bar (if applicable) */}
        {drawPercent > 0 && (
          <div
            className="rounded bg-accent-secondary/60 transition-all duration-300 flex items-center justify-center"
            style={{ width: `${drawPercent}%`, minWidth: drawPercent > 15 ? 'auto' : 0 }}
          >
            {drawPercent > 15 && (
              <span className="text-xs font-semibold text-text-inverse tabular-nums">
                {drawPercent.toFixed(0)}%
              </span>
            )}
          </div>
        )}

        {/* Away team bar */}
        <div
          className="rounded bg-gradient-to-r from-info to-info/70 transition-all duration-300 flex items-center justify-center"
          style={{ width: `${awayPercent}%`, minWidth: awayPercent > 15 ? 'auto' : 0 }}
        >
          {awayPercent > 15 && (
            <span className="text-xs font-semibold text-text-inverse tabular-nums">
              {awayPercent.toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* Labels */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="space-y-0.5">
          <p className="font-medium text-text-muted">Home</p>
          <p className="font-telemetry text-sm font-semibold text-text-primary">{homeTeam}</p>
          <p className="text-text-secondary">{homePercent.toFixed(1)}%</p>
        </div>
        <div className="space-y-0.5 text-right">
          <p className="font-medium text-text-muted">Away</p>
          <p className="font-telemetry text-sm font-semibold text-text-primary">{awayTeam}</p>
          <p className="text-text-secondary">{awayPercent.toFixed(1)}%</p>
        </div>
      </div>

      {/* Draw indicator if applicable */}
      {drawPercent > 0 && (
        <div className="border-t border-border-subtle pt-2">
          <p className="text-xs text-text-muted">
            <span className="font-medium">Draw</span>: {drawPercent.toFixed(1)}%
          </p>
        </div>
      )}
    </div>
  )
}
