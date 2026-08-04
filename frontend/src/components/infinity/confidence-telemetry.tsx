import { InfinityLabel } from './primitives/panel'

export interface ConfidenceTelemetryProps {
  probability: number
  confidence: number
  /** Per-model confidence readings — rendered as small ticks along the track so
   * "model agreement" is visible as clustering, not a separate number. */
  modelAgreement?: number[]
  trend?: 'rising' | 'falling' | 'stable'
  calibration?: number
}

function toneFor(value: number) {
  if (value >= 0.7) return 'var(--infinity-confidence-high)'
  if (value >= 0.4) return 'var(--infinity-confidence-medium)'
  return 'var(--infinity-confidence-low)'
}

/**
 * Confidence Telemetry 2.0 — a broadcast review-meter, not a segmented bar. A single
 * continuous track (a review official's evidence-strength meter) with:
 *   - a primary marker at the current confidence value
 *   - faint ticks at 25/50/75% for scale reference
 *   - small secondary ticks for each contributing model's individual reading
 *     (clustered ticks = agreement; spread ticks = disagreement, visible without a
 *     separate "model agreement" number)
 *   - a trend arrow showing whether confidence is rising, falling, or stable
 * Reusable everywhere confidence appears — predictions, match cards, ML Operations.
 */
export function InfinityConfidenceTelemetry({ probability, confidence, modelAgreement, trend, calibration }: ConfidenceTelemetryProps) {
  const tone = toneFor(confidence)
  const pct = Math.max(0, Math.min(1, confidence)) * 100

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <InfinityLabel>Confidence telemetry</InfinityLabel>
        <div className="flex items-center gap-2">
          <span className="font-infinity-telemetry text-[13px] font-semibold tabular-nums" style={{ color: tone }}>
            {Math.round(pct)}%
          </span>
          {trend && (
            <span className="font-infinity-mono text-[11px] text-infinity-text-muted" aria-label={`Trend: ${trend}`}>
              {trend === 'rising' ? '↗' : trend === 'falling' ? '↘' : '→'}
            </span>
          )}
        </div>
      </div>

      <div className="relative h-2 rounded-full bg-infinity-ground-2">
        {/* scale reference ticks */}
        {[25, 50, 75].map((mark) => (
          <span key={mark} className="absolute top-0 h-full w-px bg-infinity-border-strong" style={{ left: `${mark}%` }} aria-hidden="true" />
        ))}
        {/* filled track */}
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${pct}%`, backgroundColor: tone, transitionDuration: 'var(--infinity-motion-hold)' }}
        />
        {/* per-model agreement ticks */}
        {modelAgreement?.map((reading, i) => (
          <span
            key={i}
            className="absolute -top-0.5 h-3 w-0.5 rounded-full bg-infinity-text-primary/70"
            style={{ left: `${Math.max(0, Math.min(100, reading * 100))}%` }}
            aria-hidden="true"
          />
        ))}
        {/* current-value marker */}
        <span
          className="absolute -top-1 size-4 -translate-x-1/2 rounded-full border-2 border-infinity-ground-0"
          style={{ left: `${pct}%`, backgroundColor: tone }}
          aria-hidden="true"
        />
      </div>

      <div className="flex items-center justify-between font-infinity-mono text-[11px] text-infinity-text-muted">
        <span>Probability {(probability * 100).toFixed(1)}%</span>
        {calibration !== undefined && <span>Calibration {(calibration * 100).toFixed(0)}%</span>}
        {modelAgreement && <span>{modelAgreement.length} models</span>}
      </div>
    </div>
  )
}
