import { InfinityPanel, InfinityLabel } from '../primitives/panel'

export interface PlayerCardProps {
  name: string
  domain: 'football' | 'basketball' | 'baseball' | 'table-tennis'
  /** Real fields — populated from `PlayerSummaryDto`. */
  team?: string | null
  position?: string | null
  /** Demo-only — no fixture-to-player lineup link exists in the backend yet, so real
   * callers must omit availability/stat rather than fabricate them. */
  statLabel?: string
  statValue?: string
  available?: boolean
}

export function InfinityPlayerCard({ name, domain, team, position, statLabel, statValue, available }: PlayerCardProps) {
  const subtitle = [team, position].filter(Boolean).join(' · ')
  return (
    <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
      <div className="flex items-center gap-3">
        <div
          className="flex size-11 shrink-0 items-center justify-center rounded-infinity-sm border font-infinity-display text-[13px] font-semibold"
          style={{ borderColor: `var(--infinity-domain-${domain})40`, color: `var(--infinity-domain-${domain})` }}
          aria-hidden="true"
        >
          {name.split(' ').map((p) => p[0]).slice(0, 2).join('')}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-infinity-display text-[14px] font-semibold text-infinity-text-primary">{name}</p>
          {subtitle && <p className="truncate font-infinity-body text-[12px] text-infinity-text-secondary">{subtitle}</p>}
        </div>
        {available !== undefined && (
          <span
            className="size-1.5 shrink-0 rounded-full"
            style={{ backgroundColor: available ? 'var(--infinity-success)' : 'var(--infinity-danger)' }}
            aria-label={available ? 'Available' : 'Unavailable'}
          />
        )}
      </div>
      {statLabel && statValue && (
        <div className="mt-3 flex items-baseline justify-between border-t border-infinity-border-hairline pt-2.5">
          <InfinityLabel>{statLabel}</InfinityLabel>
          <span className="font-infinity-telemetry text-[15px] font-semibold tabular-nums text-infinity-text-primary">{statValue}</span>
        </div>
      )}
    </InfinityPanel>
  )
}
