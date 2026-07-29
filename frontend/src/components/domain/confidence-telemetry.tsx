import { cn } from '@/lib/cn'

export type ConfidenceTier = 'low' | 'medium' | 'high' | 'peak'

/**
 * TitanIQ's signature confidence visualization — an F1 broadcast-graphics sector-timing bar,
 * not a plain percentage badge. Four sectors light up cumulatively with the confidence tier;
 * "peak" (>=85%) is the rare violet tier, reserved so it actually reads as exceptional.
 *
 * This is the ONE confidence visual language for the whole platform — predictions, match cards,
 * admin model dashboards all render confidence through this component, never a bespoke meter.
 */
export function confidenceTier(confidence: number): ConfidenceTier {
  if (confidence >= 0.85) return 'peak'
  if (confidence >= 0.7) return 'high'
  if (confidence >= 0.4) return 'medium'
  return 'low'
}

const tierSegments: Record<ConfidenceTier, number> = { low: 1, medium: 2, high: 3, peak: 4 }

const tierColor: Record<ConfidenceTier, string> = {
  low: 'bg-confidence-low',
  medium: 'bg-confidence-medium',
  high: 'bg-confidence-high',
  peak: 'bg-premium',
}

const tierLabel: Record<ConfidenceTier, string> = {
  low: 'Low confidence',
  medium: 'Medium confidence',
  high: 'High confidence',
  peak: 'Peak confidence',
}

export function ConfidenceTelemetry({
  confidence,
  size = 'md',
  showValue = true,
  className,
}: {
  /** 0..1 */
  confidence: number
  size?: 'sm' | 'md'
  showValue?: boolean
  className?: string
}) {
  const tier = confidenceTier(confidence)
  const lit = tierSegments[tier]
  const pct = Math.round(confidence * 100)

  return (
    <div
      className={cn('inline-flex items-center gap-2', className)}
      role="meter"
      aria-valuenow={pct}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={tierLabel[tier]}
    >
      <div className="flex items-center gap-[3px]">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            className={cn(
              'rounded-[1px] transition-colors duration-[var(--motion-duration-base)]',
              size === 'sm' ? 'h-2.5 w-1' : 'h-3.5 w-1.5',
              i < lit ? tierColor[tier] : 'bg-border-default',
            )}
          />
        ))}
      </div>
      {showValue && (
        <span
          className={cn(
            'font-telemetry tabular-nums leading-none text-text-primary',
            size === 'sm' ? 'text-xs' : 'text-sm',
          )}
        >
          {pct}%
        </span>
      )}
    </div>
  )
}
