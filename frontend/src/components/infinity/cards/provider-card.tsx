import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityBadge } from '../primitives/badge'

export interface ProviderCardProps {
  name: string
  category: string
  status: 'healthy' | 'warning' | 'offline'
  maskedKey: string
  latencyMs: number
  requestsToday: number
  dailyLimit: number | null
}

const STATUS_TONE: Record<ProviderCardProps['status'], string> = {
  healthy: 'var(--infinity-success)',
  warning: 'var(--infinity-warning)',
  offline: 'var(--infinity-danger)',
}

export function InfinityProviderCard({ name, category, status, maskedKey, latencyMs, requestsToday, dailyLimit }: ProviderCardProps) {
  const usagePct = dailyLimit ? Math.min(1, requestsToday / dailyLimit) : null
  return (
    <InfinityPanel tone="var(--infinity-domain-operations)">
      <div className="flex items-center justify-between">
        <div>
          <p className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">{name}</p>
          <InfinityLabel className="mt-0.5 block">{category}</InfinityLabel>
        </div>
        <InfinityBadge tone={STATUS_TONE[status]}>{status}</InfinityBadge>
      </div>
      <p className="mt-3 font-infinity-mono text-[11px] text-infinity-text-muted">{maskedKey}</p>
      <div className="mt-3 grid grid-cols-2 gap-3 border-t border-infinity-border-hairline pt-2.5">
        <div>
          <InfinityLabel>Latency</InfinityLabel>
          <p className="font-infinity-telemetry text-[15px] tabular-nums text-infinity-text-primary">{latencyMs}ms</p>
        </div>
        <div>
          <InfinityLabel>Usage today</InfinityLabel>
          <p className="font-infinity-telemetry text-[15px] tabular-nums text-infinity-text-primary">
            {requestsToday}
            {dailyLimit ? ` / ${dailyLimit}` : ''}
          </p>
        </div>
      </div>
      {usagePct !== null && (
        <div className="mt-2 h-1 overflow-hidden rounded-full bg-infinity-ground-2">
          <div
            className="h-full rounded-full transition-[width] duration-500"
            style={{ width: `${usagePct * 100}%`, backgroundColor: usagePct > 0.85 ? 'var(--infinity-warning)' : 'var(--infinity-signal)' }}
          />
        </div>
      )}
    </InfinityPanel>
  )
}
