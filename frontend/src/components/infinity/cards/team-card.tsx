import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityFollowButton } from '../primitives/follow-button'

export interface TeamCardProps {
  name: string
  domain: 'football' | 'basketball' | 'baseball' | 'table-tennis'
  /** Real fields — populated from `TeamSummaryDto`. */
  country?: string | null
  venueName?: string | null
  logoUrl?: string | null
  /** Demo-only fields for the component showcase — no backend tracks league position or
   * win/draw/loss streaks yet, so real callers must omit these rather than fabricate them. */
  competition?: string
  position?: number
  form?: Array<'W' | 'D' | 'L'>
  /** Omit both to render without a follow toggle (e.g. the design showcase). */
  following?: boolean
  onToggleFollow?: () => void
}

const FORM_COLOR: Record<'W' | 'D' | 'L', string> = {
  W: 'var(--infinity-success)',
  D: 'var(--infinity-text-muted)',
  L: 'var(--infinity-danger)',
}

export function InfinityTeamCard({
  name,
  domain,
  country,
  venueName,
  logoUrl,
  competition,
  position,
  form,
  following,
  onToggleFollow,
}: TeamCardProps) {
  const subtitle = [country, venueName].filter(Boolean).join(' · ')
  return (
    <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
      {(competition || onToggleFollow) && (
        <div className="flex items-center justify-between">
          {competition ? <InfinityLabel tone={`var(--infinity-domain-${domain})`}>{competition}</InfinityLabel> : <span />}
          {onToggleFollow && <InfinityFollowButton following={!!following} onToggle={onToggleFollow} label={name} />}
        </div>
      )}
      <div className={`flex items-center justify-between ${competition || onToggleFollow ? 'mt-2' : ''}`}>
        <div className="flex min-w-0 items-center gap-2.5">
          <TeamCrestMedium name={name} logoUrl={logoUrl} />
          <p className="truncate font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{name}</p>
        </div>
        {position !== undefined && (
          <span className="shrink-0 font-infinity-telemetry text-[13px] tabular-nums text-infinity-text-muted">#{position}</span>
        )}
      </div>
      {subtitle && <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">{subtitle}</p>}
      {form && form.length > 0 && (
        <div className="mt-3 flex gap-1">
          {form.map((result, i) => (
            <span
              key={i}
              className="flex size-5 items-center justify-center rounded-infinity-sm font-infinity-mono text-[10px] font-semibold text-infinity-ground-0"
              style={{ backgroundColor: FORM_COLOR[result] }}
            >
              {result}
            </span>
          ))}
        </div>
      )}
    </InfinityPanel>
  )
}

function TeamCrestMedium({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="size-8 shrink-0 rounded-sm object-contain" loading="lazy" />
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-infinity-ground-2 font-infinity-display text-[12px] font-semibold text-infinity-text-muted"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
