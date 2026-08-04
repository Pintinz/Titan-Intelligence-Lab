import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityConfidenceRing } from '../charts/confidence-ring'

export interface PredictionCardProps {
  market: string
  selection: string
  probability: number
  confidence: number
  evidenceCount: number
}

/** Every prediction gets its own panel, never a bare percentage — the ring makes
 * confidence legible at a glance, and the evidence count is always visible so a number
 * never appears unexplained (the brief's own rule for this card). */
export function InfinityPredictionCard({ market, selection, probability, confidence, evidenceCount }: PredictionCardProps) {
  return (
    <InfinityPanel tone="var(--infinity-domain-predictions)">
      <div className="flex items-start justify-between gap-3">
        <div>
          <InfinityLabel tone="var(--infinity-domain-predictions)">{market}</InfinityLabel>
          <p className="mt-1 font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{selection}</p>
          <p className="mt-2 font-infinity-mono text-[11px] text-infinity-text-muted">
            {(probability * 100).toFixed(1)}% probability · {evidenceCount} evidence points
          </p>
        </div>
        <InfinityConfidenceRing value={confidence} size={52} />
      </div>
    </InfinityPanel>
  )
}
