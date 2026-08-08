import { Link } from 'react-router-dom'
import { Star, Sparkles, ChevronRight } from 'lucide-react'
import { CDButton } from './primitives/button'
import { CD_DOMAIN_COLOR_VAR, type DomainKey } from './primitives/domain'
import { countryFlag } from '@/lib/country-flags'
import type { EnrichedTeam } from '@/lib/hooks/use-team-intelligence'

/**
 * TeamCard — Team Intelligence's card unit, same shape discipline as `CompetitionCard`: one
 * component, two densities (`size="default" | "featured"`). League only renders when
 * `competitionName` is real (a team outside the fetched fixture window has none — never shown as
 * "Unknown League"). "Generate Intelligence" only renders when `nextFixtureId` is real: there is
 * no team-level generate action anywhere in the backend, so this deep-links to the team's actual
 * next scheduled fixture instead of pretending to generate something from the card itself.
 *
 * Visual language: flat bordered surface, crisp 1px hover state, and a single domain-colored top
 * edge that draws in on hover — Vercel's project-card grammar (precise geometry, no ambient glow)
 * translated onto Command Deck's dark tokens, in place of the glass-blur/gradient-blob treatment
 * used elsewhere. Bordered avatar tile replaces the floating crest + halo ring for the same reason.
 */
export function TeamCard({
  team,
  href,
  generateHref,
  sportDomain,
  aiReady,
  following,
  onToggleFollow,
  size = 'default',
}: {
  team: EnrichedTeam
  href: string
  generateHref: string | null
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  aiReady: boolean
  following: boolean
  onToggleFollow: () => void
  size?: 'default' | 'featured'
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const featured = size === 'featured'
  const flag = countryFlag(team.country)

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-md)] transition-colors duration-[var(--cd-motion-base)] ease-out hover:-translate-y-px"
      style={{
        padding: featured ? '1.5rem' : '1.125rem',
        backgroundColor: 'var(--cd-surface-1)',
        border: '1px solid var(--cd-border-default)',
      }}
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
            className="flex shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-sm)] border"
            style={{
              width: featured ? 52 : 40,
              height: featured ? 52 : 40,
              borderColor: 'var(--cd-border-default)',
              backgroundColor: 'var(--cd-surface-3)',
            }}
          >
            {team.logo_url ? (
              <img src={team.logo_url} alt="" className="object-contain" style={{ width: featured ? 34 : 26, height: featured ? 34 : 26 }} loading="lazy" />
            ) : (
              <span
                aria-hidden="true"
                className="font-[var(--cd-font-display)] font-semibold"
                style={{ color: domainColor, fontSize: featured ? 17 : 13 }}
              >
                {team.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <p
              className="truncate font-[var(--cd-font-display)] font-semibold"
              style={{ color: 'var(--cd-text-primary)', fontSize: featured ? 19 : 14.5 }}
            >
              {team.name}
            </p>
            {team.competitionName && (
              <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: domainColor }}>
                {team.competitionName}
              </p>
            )}
            {team.country && (
              <p className="mt-0.5 flex items-center gap-1 truncate font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
                {flag && <span aria-hidden="true">{flag}</span>}
                {team.country}
              </p>
            )}
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

      <div className="relative z-10 mt-auto flex items-center justify-between gap-2 border-t pt-3.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {aiReady ? (
          <span className="inline-flex items-center gap-1.5 font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-secondary)' }}>
            <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: domainColor }} aria-hidden="true" />
            AI ready
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
            <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: 'var(--cd-border-strong)' }} aria-hidden="true" />
            Coverage building
          </span>
        )}
        <div className="pointer-events-auto flex items-center gap-2">
          {generateHref && (
            <CDButton variant={featured ? 'primary' : 'secondary'} size="sm" href={generateHref} icon={<Sparkles className="size-3" aria-hidden="true" />}>
              Generate Intelligence
            </CDButton>
          )}
          {!generateHref && (
            <Link
              to={href}
              className="group/link inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
              style={{ color: 'var(--cd-text-secondary)' }}
            >
              View Team <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}
