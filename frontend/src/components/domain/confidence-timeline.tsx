import { cn } from '@/lib/cn'

interface ConfidencePoint {
  timestamp: string
  confidence: number
  event?: string
}

interface ConfidenceTimelineProps {
  data: ConfidencePoint[]
  height?: number
  className?: string
  showLabels?: boolean
}

/**
 * TitanIQ Confidence Timeline — shows how confidence has evolved over time.
 * Visualizes prediction certainty changes, marking key events (model updates, news impact, etc.)
 * as confidence moves up or down the timeline.
 */
export function ConfidenceTimeline({
  data,
  height = 120,
  className,
  showLabels = true,
}: ConfidenceTimelineProps) {
  if (!data || data.length === 0) {
    return (
      <div className={cn('flex items-center justify-center rounded-lg bg-bg-secondary p-4', className)}>
        <p className="text-xs text-text-muted">No confidence history available</p>
      </div>
    )
  }

  const minConfidence = Math.min(...data.map((p) => p.confidence))
  const maxConfidence = Math.max(...data.map((p) => p.confidence))
  const range = maxConfidence - minConfidence || 0.1
  const midpoint = minConfidence + range / 2

  // Normalize confidence to SVG space
  const normalize = (confidence: number) => {
    return ((confidence - minConfidence) / range) * height
  }

  // Create SVG path for smooth confidence line
  const points = data
    .map((p, i) => `${(i / (data.length - 1)) * 100},${100 - (normalize(p.confidence) / height) * 100}`)
    .join(' ')

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <svg
        viewBox={`0 0 100 100`}
        style={{ height: `${height}px`, width: '100%' }}
        className="rounded-lg border border-border-subtle bg-bg-secondary p-2"
        preserveAspectRatio="none"
      >
        {/* Grid lines */}
        <g className="opacity-20" stroke="var(--color-border-default)" strokeWidth="0.3">
          <line x1="0" y1={100 - (normalize(minConfidence) / height) * 100} x2="100" y2={100 - (normalize(minConfidence) / height) * 100} />
          <line x1="0" y1={100 - (normalize(midpoint) / height) * 100} x2="100" y2={100 - (normalize(midpoint) / height) * 100} />
          <line x1="0" y1={100 - (normalize(maxConfidence) / height) * 100} x2="100" y2={100 - (normalize(maxConfidence) / height) * 100} />
        </g>

        {/* Background gradient under curve */}
        <defs>
          <linearGradient id="confidenceGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="var(--color-confidence-high)" stopOpacity="0.3" />
            <stop offset="100%" stopColor="var(--color-confidence-high)" stopOpacity="0.05" />
          </linearGradient>
        </defs>

        {/* Line chart using polyline */}
        <polyline
          points={points}
          fill="url(#confidenceGradient)"
          stroke="var(--color-confidence-high)"
          strokeWidth="1.5"
          className="transition-all duration-300"
        />

        {/* Data point circles */}
        {data.map((p, i) => (
          <g key={i}>
            <circle
              cx={(i / (data.length - 1)) * 100}
              cy={100 - (normalize(p.confidence) / height) * 100}
              r="1.5"
              fill="var(--color-accent-primary)"
              className="transition-all duration-300 hover:r-2.5"
            />
            {p.event && (
              <title>{`${(p.confidence * 100).toFixed(0)}% — ${p.event}`}</title>
            )}
          </g>
        ))}
      </svg>

      {/* Labels */}
      {showLabels && (
        <div className="flex justify-between text-xs text-text-muted">
          <span>{(minConfidence * 100).toFixed(0)}%</span>
          <span>{(maxConfidence * 100).toFixed(0)}%</span>
        </div>
      )}
    </div>
  )
}
