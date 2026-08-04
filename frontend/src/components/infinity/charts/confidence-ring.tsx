/**
 * Confidence Ring — an arc, not a bar. Deliberately modeled on a broadcast possession-
 * ring / radar-sweep dial rather than a generic progress circle: the arc starts at
 * -90° (12 o'clock) and sweeps clockwise, with a tick mark at the current value's
 * position (the "sweep found this reading" motif), and the numeral sits inside using
 * telemetry type, tabular numerals.
 */
export function InfinityConfidenceRing({ value, size = 64 }: { value: number; size?: number }) {
  const pct = Math.max(0, Math.min(1, value))
  const stroke = Math.max(3, size * 0.08)
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - pct)
  const tone =
    pct >= 0.7 ? 'var(--infinity-confidence-high)' : pct >= 0.4 ? 'var(--infinity-confidence-medium)' : 'var(--infinity-confidence-low)'

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" role="img" aria-label={`Confidence ${Math.round(pct * 100)}%`}>
        <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--infinity-border-hairline)" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset var(--infinity-motion-hold)' }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="font-infinity-telemetry text-[13px] font-semibold tabular-nums" style={{ color: tone }}>
          {Math.round(pct * 100)}
        </span>
      </div>
    </div>
  )
}
