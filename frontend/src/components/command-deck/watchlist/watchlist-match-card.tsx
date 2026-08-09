import { Link } from 'react-router-dom'
import { Sparkles, MapPin, ChevronRight, Star } from 'lucide-react'
import { CDStatusDot } from '../primitives/status'
import { CDButton } from '../primitives/button'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'
import { resolveVerdict, type TeamRef } from '@/components/infinity/evidence-explorer'
import type { PredictionPickDto } from '@/lib/api/types'

const VALUE_LABELS: Record<string, string> = {
  YES: 'Yes',
  NO: 'No',
  OVER: 'Over',
  UNDER: 'Under',
  positive: 'Yes',
  negative: 'No',
}

function pickLabel(value: string | number, homeTeam: TeamRef, awayTeam: TeamRef): string {
  const stringValue = String(value)
  if (stringValue in VALUE_LABELS) return VALUE_LABELS[stringValue]
  return resolveVerdict(value, homeTeam, awayTeam).text
}

/**
 * WatchlistMatchCard — the followed-match unit: MATCH -> CURRENT STATE -> AI INTELLIGENCE -> ACTION,
 * per the shaped brief. Built on `DiscoveryMatchCard`'s established teams/score/status grammar
 * with a new AI Intelligence footer slot rather than forking a second fixture card language.
 * `topPick` is the fixture's single highest-confidence published prediction (or `null` if none
 * exists yet) — resolved once at the page level via `predictionsApi.picks()` + `dedupeByFixture`,
 * never a second per-card fetch.
 */
export function WatchlistMatchCard({
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
  sportDomain,
  topPick,
  following,
  onToggleFollow,
  href,
}: {
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
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  topPick: PredictionPickDto | null
  following: boolean
  onToggleFollow: () => void
  href: string
}) {
  const isLive = status === 'live'
  const hasScore = homeScore !== undefined || awayScore !== undefined
  const glowTint = domainTint(sportDomain, 12)
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const homeRef: TeamRef = { name: homeTeam, logoUrl: homeLogoUrl }
  const awayRef: TeamRef = { name: awayTeam, logoUrl: awayLogoUrl }

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5"
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
          <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: domainColor }} aria-hidden="true" />
          {competitionLogoUrl && <img src={competitionLogoUrl} alt="" className="size-3.5 shrink-0 object-contain" loading="lazy" />}
          <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
            {competition}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {isLive ? (
            <CDStatusDot label="Live" tone="live" />
          ) : (
            kickoffLabel && (
              <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                {kickoffLabel}
              </span>
            )
          )}
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault()
              onToggleFollow()
            }}
            aria-pressed={following}
            aria-label={following ? `Unfollow ${homeTeam} vs ${awayTeam}` : `Follow ${homeTeam} vs ${awayTeam}`}
            className="pointer-events-auto relative z-10 rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
            style={{ color: following ? domainColor : 'var(--cd-text-muted)' }}
          >
            <Star className="size-3.5" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="relative z-10 space-y-2.5">
        <TeamRow team={homeRef} score={homeScore} showScore={hasScore} glowTint={glowTint} />
        <TeamRow team={awayRef} score={awayScore} showScore={hasScore} glowTint={glowTint} />
      </div>

      {venue && !isLive && (
        <p className="relative z-10 flex items-center gap-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          <MapPin className="size-3 shrink-0" aria-hidden="true" />
          <span className="truncate">{venue}</span>
        </p>
      )}

      <div className="relative z-10 rounded-[var(--cd-radius-md)] border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          AI Intelligence
        </p>
        {topPick ? (
          <div className="mt-1.5 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
                {topPick.market_name}
              </p>
              <p className="truncate font-[var(--cd-font-display)] text-[14.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                {pickLabel(topPick.value, homeRef, awayRef)}
              </p>
            </div>
            <span
              className="shrink-0 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[11px] font-semibold tabular-nums"
              style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)' }}
            >
              {Math.round(topPick.confidence_composite * 100)}%
            </span>
          </div>
        ) : (
          <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            No published prediction yet
          </p>
        )}
      </div>

      <div className="relative z-10 flex items-center justify-between gap-2">
        <Link
          to={href}
          className="group/link pointer-events-auto inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
          style={{ color: 'var(--cd-text-secondary)' }}
        >
          Open Match Intelligence <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
        </Link>
        {!topPick && (
          <CDButton variant="secondary" size="sm" href={href} icon={<Sparkles className="size-3" aria-hidden="true" />} className="pointer-events-auto">
            Generate Intelligence
          </CDButton>
        )}
      </div>
    </div>
  )
}

function TeamRow({ team, score, showScore, glowTint }: { team: TeamRef; score?: number; showScore: boolean; glowTint: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="relative flex size-7 shrink-0 items-center justify-center">
          <span
            className="pointer-events-none absolute inset-[-4px] rounded-full opacity-70"
            style={{ background: `radial-gradient(circle, ${glowTint} 0%, transparent 72%)` }}
            aria-hidden="true"
          />
          {team.logoUrl ? (
            <img src={team.logoUrl} alt="" className="relative size-7 shrink-0 object-contain" loading="lazy" />
          ) : (
            <span
              aria-hidden="true"
              className="relative flex size-7 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[10px] font-semibold"
              style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
            >
              {team.name.charAt(0).toUpperCase()}
            </span>
          )}
        </span>
        <span className="truncate font-[var(--cd-font-body)] text-[13.5px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          {team.name}
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
