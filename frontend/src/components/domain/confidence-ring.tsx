import { motion } from 'framer-motion'
import { toneForScore } from '@/components/domain/confidence-meter'
import { cn } from '@/lib/cn'

const TONE_STROKE_VAR = {
  high: 'var(--color-confidence-high)',
  medium: 'var(--color-confidence-medium)',
  low: 'var(--color-confidence-low)',
} as const

const TONE_TEXT_CLASS = {
  high: 'text-confidence-high',
  medium: 'text-confidence-medium',
  low: 'text-confidence-low',
} as const

/**
 * Radial presentation of the same `ConfidenceBreakdownDto.overall` value `ConfidenceMeter`
 * already reads — composes the shared `toneForScore` threshold logic rather than recomputing it,
 * so the two components can never disagree on what counts as high/medium/low confidence.
 */
export function ConfidenceRing({ value, size = 120, label = 'Confidence', className }: { value: number; size?: number; label?: string; className?: string }) {
  const tone = toneForScore(value)
  const radius = (size - 12) / 2
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(1, value))

  return (
    <div className={cn('flex flex-col items-center gap-2', className)}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${Math.round(pct * 100)}%`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-border-subtle)"
          strokeWidth={8}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={TONE_STROKE_VAR[tone]}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circumference}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - pct) }}
          transition={{ duration: 0.6, ease: [0, 0, 0.2, 1] }}
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          className={cn('font-mono text-2xl font-semibold', TONE_TEXT_CLASS[tone])}
          fill="currentColor"
        >
          {Math.round(pct * 100)}%
        </text>
      </svg>
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
    </div>
  )
}
