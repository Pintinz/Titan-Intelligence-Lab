import { cn } from '@/lib/cn'

/** Small, low-cardinality CSS-grid heatmap — deferred in Milestone 10A for lack of a section that
 * needed it; no dedicated heatmap library added since a plain grid of colored cells is sufficient
 * at this cardinality (a handful of time buckets), not a general-purpose charting need. */
export function MomentumHeatmap({ values, className }: { values: number[]; className?: string }) {
  const max = Math.max(1, ...values)
  return (
    <div className={cn('flex gap-1', className)} role="img" aria-label="Momentum over time">
      {values.map((value, i) => {
        const intensity = Math.max(0.12, value / max)
        return (
          <div
            key={i}
            className="h-8 flex-1 rounded-sm"
            style={{ backgroundColor: `color-mix(in srgb, var(--color-accent-primary) ${Math.round(intensity * 100)}%, transparent)` }}
            title={`${value}`}
          />
        )
      })}
    </div>
  )
}
