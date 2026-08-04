import type { LucideIcon } from 'lucide-react'
import { InfinityPanel, InfinityLabel } from '../primitives/panel'

export interface MetricCardProps {
  icon: LucideIcon
  label: string
  value: string | number
  delta?: { value: string; direction: 'up' | 'down' | 'flat' }
  tone?: 'default' | 'success' | 'warning' | 'danger' | 'live'
}

const TONE_VAR: Record<NonNullable<MetricCardProps['tone']>, string> = {
  default: 'var(--infinity-signal)',
  success: 'var(--infinity-success)',
  warning: 'var(--infinity-warning)',
  danger: 'var(--infinity-danger)',
  live: 'var(--infinity-live)',
}

/** The atomic stat tile every dashboard-style surface is built from — kept flat
 * (elevation-1, hairline only) since a grid of these communicates hierarchy through
 * position and typography, not competing glows. */
export function InfinityMetricCard({ icon: Icon, label, value, delta, tone = 'default' }: MetricCardProps) {
  const color = TONE_VAR[tone]
  return (
    <InfinityPanel tone={color}>
      <div className="flex items-center justify-between">
        <InfinityLabel>{label}</InfinityLabel>
        <Icon className="size-3.5" style={{ color }} aria-hidden="true" />
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-infinity-telemetry text-[26px] font-semibold tabular-nums text-infinity-text-primary">{value}</span>
        {delta && (
          <span
            className="font-infinity-mono text-[11px]"
            style={{ color: delta.direction === 'up' ? 'var(--infinity-success)' : delta.direction === 'down' ? 'var(--infinity-danger)' : 'var(--infinity-text-muted)' }}
          >
            {delta.direction === 'up' ? '▲' : delta.direction === 'down' ? '▼' : '—'} {delta.value}
          </span>
        )}
      </div>
    </InfinityPanel>
  )
}
