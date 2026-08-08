/** CDTelemetryValue — a real tabular-numeral reading. Monospace is reserved for exactly this:
 * a measured value, never page chrome. */
export function CDTelemetryValue({
  value,
  unit,
  size = 'md',
}: {
  value: string | number
  unit?: string
  size?: 'sm' | 'md' | 'lg'
}) {
  const sizeClass = size === 'lg' ? 'text-3xl sm:text-4xl' : size === 'sm' ? 'text-lg' : 'text-2xl'
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className={`font-[var(--cd-font-tabular)] font-semibold tabular-nums ${sizeClass}`} style={{ color: 'var(--cd-text-primary)' }}>
        {value}
      </span>
      {unit && (
        <span className="font-[var(--cd-font-telemetry)] text-[11px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {unit}
        </span>
      )}
    </span>
  )
}

/** CDDistributionBar — one ranked row of a probability distribution: real label, real bar
 * length, real tabular percentage. Sofascore match-stat-bar convention (a labeled horizontal
 * fill, not a skeuomorphic meter) applied to "Alternative Outcomes" instead of a market-depth
 * ladder — the depth-bar form without the trading-terminal function. */
export function CDDistributionBar({
  label,
  probability,
  isTop,
}: {
  label: string
  probability: number
  isTop: boolean
}) {
  const pct = Math.max(0, Math.min(1, probability)) * 100
  return (
    <div className="flex items-center gap-3">
      <span
        className="w-24 shrink-0 truncate font-[var(--cd-font-body)] text-[12px] sm:w-28"
        style={{ color: isTop ? 'var(--cd-text-primary)' : 'var(--cd-text-secondary)', fontWeight: isTop ? 600 : 400 }}
      >
        {label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }}>
        <div
          className="h-full rounded-full transition-[width] duration-[var(--cd-motion-deliberate)] ease-out"
          style={{ width: `${pct}%`, backgroundColor: isTop ? 'var(--cd-accent)' : 'var(--cd-border-strong)' }}
        />
      </div>
      <span
        className="w-11 shrink-0 text-right font-[var(--cd-font-tabular)] text-[12px] font-medium tabular-nums"
        style={{ color: isTop ? 'var(--cd-text-primary)' : 'var(--cd-text-muted)' }}
      >
        {pct.toFixed(1)}%
      </span>
    </div>
  )
}
