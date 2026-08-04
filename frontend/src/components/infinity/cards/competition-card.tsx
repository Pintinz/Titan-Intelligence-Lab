import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityFollowButton } from '../primitives/follow-button'

export interface CompetitionCardProps {
  name: string
  domain: 'football' | 'basketball' | 'baseball' | 'table-tennis'
  /** Real fields — populated from `CompetitionSummaryDto`. */
  type?: string
  country?: string | null
  tier?: number | null
  logoUrl?: string | null
  /** Omit both to render without a follow toggle (e.g. the design showcase). */
  following?: boolean
  onToggleFollow?: () => void
}

export function InfinityCompetitionCard({ name, domain, type, country, tier, logoUrl, following, onToggleFollow }: CompetitionCardProps) {
  return (
    <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
      {(type || onToggleFollow) && (
        <div className="flex items-center justify-between">
          {type ? <InfinityLabel tone={`var(--infinity-domain-${domain})`}>{type}</InfinityLabel> : <span />}
          {onToggleFollow && <InfinityFollowButton following={!!following} onToggle={onToggleFollow} label={name} />}
        </div>
      )}
      <div className={`flex items-baseline justify-between ${type || onToggleFollow ? 'mt-1.5' : ''}`}>
        <div className="flex min-w-0 items-center gap-2">
          <CompetitionCrest name={name} logoUrl={logoUrl} />
          <p className="truncate font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{name}</p>
        </div>
        {tier != null && (
          <span className="shrink-0 font-infinity-telemetry text-[13px] tabular-nums text-infinity-text-muted">Tier {tier}</span>
        )}
      </div>
      {country && <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">{country}</p>}
    </InfinityPanel>
  )
}

function CompetitionCrest({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="size-5 shrink-0 object-contain" loading="lazy" />
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-5 shrink-0 items-center justify-center rounded-sm bg-infinity-ground-2 font-infinity-mono text-[9px] font-semibold text-infinity-text-muted"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
