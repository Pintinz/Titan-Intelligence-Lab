import { Link } from 'react-router-dom'
import { Sparkles, MapPin, ChevronRight, Star } from 'lucide-react'
import { CDStatusDot } from '../primitives/status'
import { CDButton } from '../primitives/button'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'

export interface DiscoveryMatchCardProps {
  competition: string
  competitionLogoUrl?: string | null
  status: 'live' | 'upcoming' | 'completed'
  kickoffLabel?: string
  venue?: string | null
  homeTeam: string
  awayTeam: string
  homeScore?: number
  awayScore?: number
  homeLogoUrl?: string | null
  awayLogoUrl?: string | null
  /** Whether TitanIQ has a trained market for this fixture's sport — a sport-level signal
   * (every fixture in a covered sport shares it today), never invented per-fixture. */
  aiAvailable?: boolean
  /** Optional sport-category tint (football/basketball/baseball/table-tennis) for the
   * competition-label dot and crest glow — opt-in so single-sport pages (Match Discovery,
   * Live) that already establish sport via their own page chrome keep the neutral indigo glow,
   * while cross-sport surfaces (Mission Control) can tag each card by sport at a glance. */
  sportDomain?: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  following?: boolean
  onToggleFollow?: () => void
  href: string
}

/**
 * DiscoveryMatchCard — the Command Deck's fixture-scan unit: a bounded instrument reading you
 * scan quickly to pick a match, not a broadcast-style card. Same panel grammar (bounded surface,
 * glass depth, structural elevation) as the Prediction Laboratory's market cards, so
 * Discovery and Match Intelligence read as one continuous instrument, not two visual worlds.
 */
export function DiscoveryMatchCard({
  competition,
  competitionLogoUrl,
  status,
  kickoffLabel,
  venue,
  homeTeam,
  awayTeam,
  homeScore,
  awayScore,
  homeLogoUrl,
  awayLogoUrl,
  aiAvailable,
  sportDomain,
  following,
  onToggleFollow,
  href,
}: DiscoveryMatchCardProps) {
  const isLive = status === 'live'
  const hasScore = homeScore !== undefined || awayScore !== undefined
  const glowTint = sportDomain ? domainTint(sportDomain, 12) : 'var(--cd-accent-muted)'

  return (
    <div
      className="group relative flex flex-col gap-3.5 overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5"
      style={{
        background: 'var(--cd-card-surface)',
        border: `1px solid ${isLive ? 'var(--cd-live-muted)' : 'var(--cd-card-border)'}`,
        boxShadow: isLive ? 'var(--cd-glow-live)' : 'var(--cd-card-shadow)',
      }}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-[var(--cd-motion-base)] group-hover:opacity-100"
        style={{ background: `radial-gradient(140% 90% at 0% 0%, ${glowTint}, transparent 62%)` }}
        aria-hidden="true"
      />

      <Link to={href} aria-label={`${homeTeam} vs ${awayTeam}`} className="absolute inset-0 z-0" />

      <div className="relative z-10 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {sportDomain && (
            <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: CD_DOMAIN_COLOR_VAR[sportDomain] }} aria-hidden="true" />
          )}
          {competitionLogoUrl && <img src={competitionLogoUrl} alt="" className="size-3.5 shrink-0 object-contain" loading="lazy" />}
          <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
            {competition}
          </span>
        </div>
        {isLive ? (
          <CDStatusDot label="Live" tone="live" />
        ) : (
          kickoffLabel && (
            <span className="shrink-0 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              {kickoffLabel}
            </span>
          )
        )}
      </div>

      <div className="relative z-10 space-y-2.5">
        <TeamRow name={homeTeam} score={homeScore} logoUrl={homeLogoUrl} showScore={hasScore} glowTint={glowTint} />
        <TeamRow name={awayTeam} score={awayScore} logoUrl={awayLogoUrl} showScore={hasScore} glowTint={glowTint} />
      </div>

      <div className="relative z-10 flex items-center justify-between gap-2 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <span className="flex min-w-0 items-center gap-1 truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          {venue && !isLive && (
            <>
              <MapPin className="size-3 shrink-0" aria-hidden="true" />
              <span className="truncate">{venue}</span>
            </>
          )}
        </span>
        <div className="pointer-events-auto flex shrink-0 items-center gap-2">
          {onToggleFollow && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault()
                onToggleFollow()
              }}
              aria-pressed={!!following}
              aria-label={following ? `Unfollow ${homeTeam} vs ${awayTeam}` : `Follow ${homeTeam} vs ${awayTeam}`}
              className="rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
              style={{ color: following ? 'var(--cd-accent)' : 'var(--cd-text-muted)' }}
            >
              <Star className="size-3.5" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
            </button>
          )}
          {aiAvailable && (
            <span
              className="inline-flex items-center gap-1 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.05em]"
              style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)', boxShadow: '0 0 0 1px var(--cd-accent-strong) inset' }}
            >
              <Sparkles className="size-2.5" aria-hidden="true" />
              AI ready
            </span>
          )}
        </div>
      </div>

      <div className="relative z-10 flex items-center justify-between gap-2">
        <Link
          to={href}
          className="group/link inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
          style={{ color: 'var(--cd-text-secondary)' }}
        >
          View match <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
        </Link>
        {aiAvailable && (
          <CDButton variant="primary" size="sm" href={href} icon={<Sparkles className="size-3" aria-hidden="true" />} className="pointer-events-auto">
            Generate Intelligence
          </CDButton>
        )}
      </div>
    </div>
  )
}

function TeamRow({
  name,
  score,
  logoUrl,
  showScore,
  glowTint,
}: {
  name: string
  score?: number
  logoUrl?: string | null
  showScore: boolean
  glowTint: string
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="relative flex size-7 shrink-0 items-center justify-center">
          <span
            className="pointer-events-none absolute inset-[-4px] rounded-full opacity-70"
            style={{ background: `radial-gradient(circle, ${glowTint} 0%, transparent 72%)` }}
            aria-hidden="true"
          />
          {logoUrl ? (
            <img src={logoUrl} alt="" className="relative size-7 shrink-0 object-contain" loading="lazy" />
          ) : (
            <span
              aria-hidden="true"
              className="relative flex size-7 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[10px] font-semibold"
              style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
            >
              {name.charAt(0).toUpperCase()}
            </span>
          )}
        </span>
        <span className="truncate font-[var(--cd-font-body)] text-[13.5px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          {name}
        </span>
      </div>
      {showScore && (
        <span className="shrink-0 font-[var(--cd-font-tabular)] text-[15px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
          {score ?? '–'}
        </span>
      )}
    </div>
  )
}
