import { Link } from 'react-router-dom'
import { Star, ChevronRight } from 'lucide-react'
import { CD_DOMAIN_COLOR_VAR, type DomainKey } from '../primitives/domain'
import { countryFlag } from '@/lib/country-flags'
import type { Outcome } from '@/lib/watchlist/form'
import type { TeamSummaryDto, FixtureSummaryDto } from '@/lib/api/types'

const OUTCOME_COLOR: Record<Outcome, string> = {
  W: 'var(--cd-positive)',
  D: 'var(--cd-text-muted)',
  L: 'var(--cd-live)',
}

/**
 * WatchlistTeamCard — `TeamCard`'s established flat-bordered, Vercel-restraint grammar
 * (hairline border, domain-accent top edge on hover), restructured around the shaped brief's
 * priority for a followed team: identity -> next match -> recent form -> deep-intelligence
 * action. `nextMatch`/`form` are `null`/empty when no real data exists — rendered as an honest
 * "unavailable" line, never a placeholder.
 */
export function WatchlistTeamCard({
  team,
  href,
  sportDomain,
  nextMatch,
  form,
  following,
  onToggleFollow,
}: {
  team: TeamSummaryDto
  href: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  nextMatch: FixtureSummaryDto | null
  form: Outcome[]
  following: boolean
  onToggleFollow: () => void
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const flag = countryFlag(team.country)
  const opponent = nextMatch ? (nextMatch.home_team.id === team.id ? nextMatch.away_team : nextMatch.home_team) : null
  const isHome = nextMatch ? nextMatch.home_team.id === team.id : null

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-md)] p-[1.125rem] transition-colors duration-[var(--cd-motion-base)] ease-out hover:-translate-y-px"
      style={{ backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-default)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = domainColor
        e.currentTarget.style.backgroundColor = 'var(--cd-surface-2)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--cd-border-default)'
        e.currentTarget.style.backgroundColor = 'var(--cd-surface-1)'
      }}
    >
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-[2px] origin-left scale-x-0 transition-transform duration-[var(--cd-motion-base)] ease-out group-hover:scale-x-100"
        style={{ backgroundColor: domainColor }}
        aria-hidden="true"
      />

      <Link to={href} aria-label={team.name} className="absolute inset-0 z-0" />

      <div className="relative z-10 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-sm)] border"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-3)' }}
          >
            {team.logo_url ? (
              <img src={team.logo_url} alt="" className="size-6.5 object-contain" loading="lazy" />
            ) : (
              <span aria-hidden="true" className="font-[var(--cd-font-display)] text-[13px] font-semibold" style={{ color: domainColor }}>
                {team.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <p className="truncate font-[var(--cd-font-display)] text-[14.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
              {team.name}
            </p>
            <p className="mt-0.5 flex items-center gap-1 truncate font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
              {flag && <span aria-hidden="true">{flag}</span>}
              {team.country ? `${team.country} · ` : ''}
              <span style={{ color: domainColor }}>{sportDomain === 'table-tennis' ? 'Table Tennis' : sportDomain[0].toUpperCase() + sportDomain.slice(1)}</span>
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
          aria-label={following ? `Unfollow ${team.name}` : `Follow ${team.name}`}
          className="pointer-events-auto relative z-10 shrink-0 rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
          style={{ color: following ? domainColor : 'var(--cd-text-muted)' }}
        >
          <Star className="size-4" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      </div>

      <div className="relative z-10 rounded-[var(--cd-radius-sm)] border px-3 py-2.5" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}>
        <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          Next match
        </p>
        {nextMatch && opponent ? (
          <>
            <p className="mt-1 truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
              {isHome ? `${team.name} vs ${opponent.name}` : `${opponent.name} vs ${team.name}`}
            </p>
            <p className="mt-0.5 truncate font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
              {nextMatch.competition_name} · {new Date(nextMatch.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
            </p>
          </>
        ) : (
          <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            Next fixture unavailable
          </p>
        )}
      </div>

      <div className="relative z-10">
        <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          Recent form
        </p>
        {form.length > 0 ? (
          <div className="mt-1.5 flex items-center gap-1">
            {form.map((outcome, i) => (
              <span
                key={i}
                className="flex size-5 items-center justify-center rounded-[3px] font-[var(--cd-font-tabular)] text-[10px] font-bold"
                style={{ backgroundColor: OUTCOME_COLOR[outcome], color: 'var(--cd-text-inverse)' }}
              >
                {outcome}
              </span>
            ))}
          </div>
        ) : (
          <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            Recent form unavailable
          </p>
        )}
      </div>

      <Link
        to={href}
        className="group/link pointer-events-auto relative z-10 mt-auto flex items-center gap-0.5 border-t pt-3 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
        style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-secondary)' }}
      >
        Open team intelligence
        <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
      </Link>
    </div>
  )
}
