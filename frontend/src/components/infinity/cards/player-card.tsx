import { InfinityLabel } from '../primitives/panel'
import { cn } from '@/lib/cn'

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

/** Identity-first shell — a flat hairline card with a domain-tinted initials medallion, not the
 * corner-tick evidence-panel treatment: a roster is scanned for who's who, not read for proof. */
export function InfinityPlayerCard({ name, domain, team, position, statLabel, statValue, available }: PlayerCardProps) {
  const subtitle = [team, position].filter(Boolean).join(' · ')
  const tone = `var(--infinity-domain-${domain})`
  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-infinity-lg border border-infinity-border-hairline bg-infinity-ground-1 p-4',
        'transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-infinity-border-default',
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className="flex size-11 shrink-0 items-center justify-center rounded-infinity-sm border font-infinity-display text-[13px] font-semibold"
          style={{ borderColor: `${tone}40`, color: tone }}
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
            className="shrink-0 rounded-infinity-full border px-1.5 py-0.5 font-infinity-mono text-[9px] font-semibold uppercase tracking-[0.04em]"
            style={
              available
                ? { color: 'var(--infinity-success)', borderColor: 'var(--infinity-success)40', backgroundColor: 'var(--infinity-success)14' }
                : { color: 'var(--infinity-danger)', borderColor: 'var(--infinity-danger)40', backgroundColor: 'var(--infinity-danger)14' }
            }
          >
            {available ? 'Available' : 'Out'}
          </span>
        )}
      </div>
      {statLabel && statValue && (
        <div className="mt-3 flex items-baseline justify-between border-t border-infinity-border-hairline pt-2.5">
          <InfinityLabel>{statLabel}</InfinityLabel>
          <span className="font-infinity-telemetry text-[15px] font-semibold tabular-nums text-infinity-text-primary">{statValue}</span>
        </div>
      )}
    </div>
  )
}
