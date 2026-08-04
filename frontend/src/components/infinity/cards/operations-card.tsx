import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityBadge } from '../primitives/badge'

export interface OperationsCardProps {
  system: string
  health: 'healthy' | 'degraded' | 'down'
  uptimePct: number
  detail: string
}

const HEALTH_TONE: Record<OperationsCardProps['health'], string> = {
  healthy: 'var(--infinity-success)',
  degraded: 'var(--infinity-warning)',
  down: 'var(--infinity-danger)',
}

export function InfinityOperationsCard({ system, health, uptimePct, detail }: OperationsCardProps) {
  return (
    <InfinityPanel tone="var(--infinity-domain-infrastructure)">
      <div className="flex items-center justify-between">
        <InfinityLabel>{system}</InfinityLabel>
        <InfinityBadge tone={HEALTH_TONE[health]}>{health}</InfinityBadge>
      </div>
      <p className="mt-2 font-infinity-telemetry text-[22px] font-semibold tabular-nums text-infinity-text-primary">
        {uptimePct.toFixed(2)}%
      </p>
      <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">{detail}</p>
    </InfinityPanel>
  )
}
