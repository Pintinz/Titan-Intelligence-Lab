import { Link } from 'react-router-dom'
import { Sparkles, MapPin, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/cn'
import { DOMAIN_COLOR_VAR, type DomainKey } from '../primitives/badge'
import { InfinityFollowButton } from '../primitives/follow-button'

export interface MatchCardProps {
  sport: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  competition: string
  competitionLogoUrl?: string | null
  status: 'live' | 'upcoming' | 'completed'
  minute?: string
  kickoff?: string
  venue?: string | null
  homeTeam: string
  awayTeam: string
  homeScore?: number
  awayScore?: number
  homeLogoUrl?: string | null
  awayLogoUrl?: string | null
  /** Whether TitanIQ has a market ready for this fixture — shows the AI badge when true. */
  aiAvailable?: boolean
  /** Omit both to render without a follow toggle (e.g. the design showcase). */
  following?: boolean
  onToggleFollow?: () => void
  /** Match detail route — when set, the whole card is a stretched link to it (keyboard/
   * screen-reader users get the explicit "View match" link below as the named target) and
   * "Generate Intelligence" becomes a second, equally real link to the same destination —
   * Match Intelligence is the only place predictions actually render, so there's nowhere
   * else honest to send that click. */
  href?: string
}

/** The card every discovery surface (Matches, Live, Mission Control) is built from — soft,
 * rounded, elevated, built to be scanned fast while picking a match, not read for evidence.
 * Deliberately a different shell than `InfinityPanel`'s broadcast corner-tick treatment,
 * which stays reserved for Match Intelligence's review-panel/telemetry surfaces: a card
 * you're scanning to choose a match reads differently than a panel you're reading for proof. */
export function InfinityMatchCard({
  sport,
  competition,
  competitionLogoUrl,
  status,
  minute,
  kickoff,
  venue,
  homeTeam,
  awayTeam,
  homeScore,
  awayScore,
  homeLogoUrl,
  awayLogoUrl,
  aiAvailable,
  following,
  onToggleFollow,
  href,
}: MatchCardProps) {
  const isLive = status === 'live'
  const tone = DOMAIN_COLOR_VAR[sport]
  // Top edge echoes the status pill in a glance-able accent, the same "tone = at-a-glance
  // state" language the team page's Record cards use — live is always the live-red regardless
  // of sport, upcoming carries the sport's own color, completed stays neutral/settled.
  const edgeTone = isLive ? 'var(--infinity-live)' : status === 'upcoming' ? tone : 'var(--infinity-text-muted)'

  return (
    <div
      className={cn(
        'group relative flex flex-col gap-3 overflow-hidden rounded-infinity-2xl border border-infinity-border-hairline bg-infinity-ground-1 p-4',
        'shadow-[var(--infinity-elevation-2)] transition-[transform,box-shadow] duration-200 ease-out',
        'hover:-translate-y-0.5 hover:shadow-[var(--infinity-elevation-signal)]',
      )}
      style={isLive ? { boxShadow: 'var(--infinity-elevation-live)' } : undefined}
    >
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 z-10 h-[2px]"
        style={{ background: `linear-gradient(90deg, ${edgeTone}, transparent)` }}
      />
      {href && (
        <Link to={href} aria-label={`${homeTeam} vs ${awayTeam}`} className="absolute inset-0 z-0 rounded-infinity-2xl" />
      )}

      <div className="relative z-10 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {competitionLogoUrl ? (
            <img src={competitionLogoUrl} alt="" className="size-4 shrink-0 rounded-full object-contain" loading="lazy" />
          ) : null}
          <span
            className="truncate font-infinity-body text-[11px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted"
            style={{ color: tone }}
          >
            {competition}
          </span>
        </div>
        <div className="pointer-events-auto flex shrink-0 items-center gap-1.5">
          {isLive ? (
            <span className="inline-flex items-center gap-1 rounded-infinity-full bg-infinity-live-muted px-2 py-0.5 font-infinity-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-infinity-live">
              <span className="size-1.5 animate-pulse rounded-full bg-infinity-live" aria-hidden="true" />
              {minute ?? 'Live'}
            </span>
          ) : (
            <span className="font-infinity-mono text-[11px] text-infinity-text-muted">
              {status === 'upcoming' ? kickoff : 'Full time'}
            </span>
          )}
          {onToggleFollow && (
            <InfinityFollowButton following={!!following} onToggle={onToggleFollow} label={`${homeTeam} vs ${awayTeam}`} />
          )}
        </div>
      </div>

      <div className="relative z-0 space-y-2.5">
        <TeamRow name={homeTeam} score={homeScore} logoUrl={homeLogoUrl} />
        <TeamRow name={awayTeam} score={awayScore} logoUrl={awayLogoUrl} />
      </div>

      {(venue || aiAvailable) && (
        <div className="relative z-10 flex items-center justify-between gap-2 border-t border-infinity-border-hairline pt-2.5">
          <span className="flex min-w-0 items-center gap-1 truncate font-infinity-mono text-[10px] text-infinity-text-muted">
            {venue && !isLive && (
              <>
                <MapPin className="size-3 shrink-0" aria-hidden="true" />
                <span className="truncate">{venue}</span>
              </>
            )}
          </span>
          {aiAvailable && (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded-infinity-full border px-1.5 py-0.5 font-infinity-body text-[10px] font-semibold uppercase tracking-[0.05em]"
              style={{ color: 'var(--infinity-domain-predictions)', borderColor: 'var(--infinity-domain-predictions)40', backgroundColor: 'var(--infinity-domain-predictions)14' }}
            >
              <Sparkles className="size-3" aria-hidden="true" />
              AI ready
            </span>
          )}
        </div>
      )}

      {href && (
        <div className="relative z-10 flex items-center justify-between gap-2 pt-0.5">
          <Link
            to={href}
            className="inline-flex items-center gap-0.5 font-infinity-body text-[11px] font-medium text-infinity-text-secondary transition-colors hover:text-infinity-text-primary"
          >
            View match <ChevronRight className="size-3" aria-hidden="true" />
          </Link>
          {aiAvailable && (
            <Link
              to={href}
              className="inline-flex items-center gap-1 rounded-infinity-full px-2.5 py-1 font-infinity-body text-[11px] font-semibold text-infinity-text-inverse transition-opacity hover:opacity-90"
              style={{ backgroundColor: 'var(--infinity-domain-predictions)' }}
            >
              <Sparkles className="size-3" aria-hidden="true" />
              Generate Intelligence
            </Link>
          )}
        </div>
      )}
    </div>
  )
}

function TeamRow({ name, score, logoUrl }: { name: string; score?: number; logoUrl?: string | null }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <TeamCrest name={name} logoUrl={logoUrl} />
        <span className="truncate font-infinity-body text-[14px] font-medium text-infinity-text-primary">{name}</span>
      </div>
      <span className="shrink-0 font-infinity-telemetry text-[16px] font-semibold tabular-nums text-infinity-text-primary">
        {score ?? '–'}
      </span>
    </div>
  )
}

function TeamCrest({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  if (logoUrl) {
    return <img src={logoUrl} alt="" className="size-7 shrink-0 rounded-full object-contain" loading="lazy" />
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-7 shrink-0 items-center justify-center rounded-full bg-infinity-ground-2 font-infinity-mono text-[11px] font-semibold text-infinity-text-muted"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
