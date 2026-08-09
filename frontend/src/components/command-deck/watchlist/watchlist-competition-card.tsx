import { Link } from 'react-router-dom'
import { Star, ChevronRight } from 'lucide-react'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'
import type { CompetitionSummaryDto, FixtureSummaryDto } from '@/lib/api/types'

/**
 * WatchlistCompetitionCard — `CompetitionCard`'s established glass/domain-tinted grammar,
 * restructured around the shaped brief's priority for a followed competition: identity -> real
 * next fixtures -> deep-intelligence action. `nextFixtures` is whatever the backend actually has
 * scheduled (0, 1, or several) — never padded to a fixed count.
 */
export function WatchlistCompetitionCard({
  competition,
  href,
  sportDomain,
  nextFixtures,
  following,
  onToggleFollow,
}: {
  competition: CompetitionSummaryDto
  href: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  nextFixtures: FixtureSummaryDto[]
  following: boolean
  onToggleFollow: () => void
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-2xl)] p-5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-1"
      style={{ background: 'var(--cd-card-surface)', border: `1px solid ${domainTint(sportDomain, 22)}`, boxShadow: 'var(--cd-card-shadow)' }}
      onMouseEnter={(e) => (e.currentTarget.style.boxShadow = `${domainTint(sportDomain, 26)} 0 0 0 1px inset, var(--cd-card-shadow-hover)`)}
      onMouseLeave={(e) => (e.currentTarget.style.boxShadow = 'var(--cd-card-shadow)')}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-[var(--cd-motion-base)] group-hover:opacity-100"
        style={{ background: `radial-gradient(140% 90% at 0% 0%, ${domainTint(sportDomain, 14)}, transparent 62%)` }}
        aria-hidden="true"
      />

      <Link to={href} aria-label={competition.name} className="absolute inset-0 z-0" />

      <div className="relative z-10 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="relative flex size-11 shrink-0 items-center justify-center">
            <span
              className="pointer-events-none absolute inset-[-6px] rounded-full opacity-70"
              style={{ background: `radial-gradient(circle, ${domainTint(sportDomain, 20)} 0%, transparent 72%)` }}
              aria-hidden="true"
            />
            {competition.logo_url ? (
              <img src={competition.logo_url} alt="" className="relative size-8 object-contain" loading="lazy" />
            ) : (
              <span
                aria-hidden="true"
                className="relative flex size-8 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[12px] font-semibold"
                style={{ backgroundColor: 'var(--cd-surface-3)', color: domainColor }}
              >
                {competition.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <p className="truncate font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
              {competition.name}
            </p>
            <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              {[competition.country, sportDomain === 'table-tennis' ? 'Table Tennis' : sportDomain[0].toUpperCase() + sportDomain.slice(1), competition.type]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.preventDefault()
            onToggleFollow()
          }}
          aria-pressed={following}
          aria-label={following ? `Unfollow ${competition.name}` : `Follow ${competition.name}`}
          className="pointer-events-auto relative z-10 shrink-0 rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
          style={{ color: following ? domainColor : 'var(--cd-text-muted)' }}
        >
          <Star className="size-4" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      </div>

      <div className="relative z-10">
        <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          Next fixtures
        </p>
        {nextFixtures.length > 0 ? (
          <div className="mt-1.5 space-y-1.5">
            {nextFixtures.map((f) => (
              <div key={f.id} className="flex items-center justify-between gap-2 rounded-[var(--cd-radius-sm)] px-2.5 py-1.5" style={{ backgroundColor: 'var(--cd-surface-2)' }}>
                <span className="truncate font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-primary)' }}>
                  {f.home_team.name} vs {f.away_team.name}
                </span>
                <span className="shrink-0 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                  {new Date(f.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            Next fixtures unavailable
          </p>
        )}
      </div>

      <Link
        to={href}
        className="group/link pointer-events-auto relative z-10 mt-auto flex items-center gap-0.5 border-t pt-3.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
        style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-secondary)' }}
      >
        Open competition intelligence
        <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
      </Link>
    </div>
  )
}
