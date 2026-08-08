/**
 * CDConfidenceGauge — a real 270° dial gauge (Sofascore match-stat-arc convention, not a
 * skeuomorphic instrument dial), reading a real 0–1 composite confidence score. The track's 90°
 * gap sits at the bottom so the gauge reads like an instrument face, not a full ring (keeps it
 * visually distinct from InfinityConfidenceRing, a deliberate departure per the direction, not
 * an accidental near-copy). Three confidence bands share the same green/amber language
 * Confidence Drivers already uses — never a fourth "red danger" band, since a published
 * prediction already cleared the market's confidence threshold.
 */
export function CDConfidenceGauge({
  value,
  size = 128,
  label,
}: {
  /** 0–1 composite confidence */
  value: number
  size?: number
  label?: string
}) {
  const clamped = Math.max(0, Math.min(1, value))
  const strokeWidth = size * 0.09
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const arcFraction = 0.75 // 270 of 360 degrees
  const trackLength = circumference * arcFraction
  const progressLength = trackLength * clamped

  const tone = clamped >= 0.7 ? 'var(--cd-positive)' : clamped >= 0.5 ? 'var(--cd-negative)' : 'var(--cd-text-muted)'
  const center = size / 2

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-[135deg]">
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke="var(--cd-border-default)"
          strokeWidth={strokeWidth}
          strokeDasharray={`${trackLength} ${circumference}`}
          strokeLinecap="round"
        />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={strokeWidth}
          strokeDasharray={`${progressLength} ${circumference}`}
          strokeLinecap="round"
          className="transition-[stroke-dasharray] duration-[var(--cd-motion-deliberate)] ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span
          className="font-[var(--cd-font-tabular)] font-semibold tabular-nums"
          style={{ color: 'var(--cd-text-primary)', fontSize: size * 0.26 }}
        >
          {Math.round(clamped * 100)}
        </span>
        {label && (
          <span
            className="mt-0.5 font-[var(--cd-font-telemetry)] uppercase tracking-[0.08em]"
            style={{ color: 'var(--cd-text-muted)', fontSize: size * 0.08 }}
          >
            {label}
          </span>
        )}
      </div>
    </div>
  )
}
