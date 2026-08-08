import { Link } from 'react-router-dom'
import { Star, Sparkles, Users, ChevronRight } from 'lucide-react'
import { CDStatusDot } from './primitives/status'
import { CDButton } from './primitives/button'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from './primitives/domain'
import type { EnrichedCompetition } from '@/lib/hooks/use-competition-intelligence'

/**
 * CompetitionCard — the Competition Center's fixture-scan unit for competitions instead of
 * matches: a bounded glass instrument, never a text link. `size="featured"` (tier-1 competitions)
 * gets a larger crest, bigger type, and a two-column stat row; the default grid card carries the
 * same real fields at a denser size — one component, two densities, so the two never drift.
 * Every stat traces to `EnrichedCompetition` (derived from real fetched fixtures, see the hook) —
 * `teamsFeatured` is deliberately labeled, never "Teams", since it's an observed count, not a
 * claimed roster size.
 */
export function CompetitionCard({
  competition,
  href,
  sportDomain,
  aiReady,
  following,
  onToggleFollow,
  size = 'default',
}: {
  competition: EnrichedCompetition
  href: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  aiReady: boolean
  following: boolean
  onToggleFollow: () => void
  size?: 'default' | 'featured'
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const featured = size === 'featured'

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-2xl)] backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-1"
      style={{
        padding: featured ? '1.75rem' : '1.25rem',
        background: 'var(--cd-card-surface)',
        border: `1px solid ${domainTint(sportDomain, 22)}`,
        boxShadow: 'var(--cd-card-shadow)',
      }}
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
          <span className="relative flex shrink-0 items-center justify-center" style={{ width: featured ? 56 : 40, height: featured ? 56 : 40 }}>
            <span
              className="pointer-events-none absolute inset-[-6px] rounded-full opacity-70"
              style={{ background: `radial-gradient(circle, ${domainTint(sportDomain, 20)} 0%, transparent 72%)` }}
              aria-hidden="true"
            />
            {competition.logo_url ? (
              <img src={competition.logo_url} alt="" className="relative object-contain" style={{ width: featured ? 44 : 32, height: featured ? 44 : 32 }} loading="lazy" />
            ) : (
              <span
                aria-hidden="true"
                className="relative flex items-center justify-center rounded-full font-[var(--cd-font-display)] font-semibold"
                style={{ width: featured ? 44 : 32, height: featured ? 44 : 32, backgroundColor: 'var(--cd-surface-3)', color: domainColor, fontSize: featured ? 16 : 12 }}
              >
                {competition.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <p
              className="truncate font-[var(--cd-font-display)] font-semibold"
              style={{ color: 'var(--cd-text-primary)', fontSize: featured ? 19 : 14.5 }}
            >
              {competition.name}
            </p>
            {(competition.country || competition.tier != null) && (
              <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                {[competition.country, competition.tier != null ? `Tier ${competition.tier}` : null].filter(Boolean).join(' · ')}
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
          aria-label={following ? `Unfollow ${competition.name}` : `Follow ${competition.name}`}
          className="pointer-events-auto relative z-10 shrink-0 rounded-[var(--cd-radius-sm)] p-1 transition-colors duration-[var(--cd-motion-snap)]"
          style={{ color: following ? domainColor : 'var(--cd-text-muted)' }}
        >
          <Star className="size-4" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
        </button>
      </div>

      <div className={`relative z-10 grid gap-2.5 ${featured ? 'grid-cols-4' : 'grid-cols-3'}`}>
        <StatCell label="Live" value={competition.liveCount} tone={competition.liveCount > 0 ? 'live' : undefined} />
        <StatCell label="Upcoming" value={competition.upcomingCount} />
        <StatCell label="Completed" value={competition.completedCount} />
        {featured && <StatCell label="Teams featured" value={competition.teamsFeatured} icon={Users} />}
      </div>

      {!featured && competition.teamsFeatured > 0 && (
        <p className="relative z-10 flex items-center gap-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          <Users className="size-3" aria-hidden="true" />
          {competition.teamsFeatured} teams featured
        </p>
      )}

      <div className="relative z-10 mt-auto flex items-center justify-between gap-2 border-t pt-3.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {aiReady ? (
          <span
            className="inline-flex items-center gap-1 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.05em]"
            style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)', boxShadow: '0 0 0 1px var(--cd-accent-strong) inset' }}
          >
            <Sparkles className="size-2.5" aria-hidden="true" />
            AI ready
          </span>
        ) : (
          <span className="font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
            Coverage building
          </span>
        )}
        {featured ? (
          <CDButton variant="primary" size="sm" href={href} className="pointer-events-auto" icon={<ChevronRight className="size-3" aria-hidden="true" />}>
            View Competition
          </CDButton>
        ) : (
          <Link
            to={href}
            className="group/link pointer-events-auto inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
            style={{ color: 'var(--cd-text-secondary)' }}
          >
            View Competition <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
          </Link>
        )}
      </div>
    </div>
  )
}

function StatCell({
  label,
  value,
  tone,
  icon: Icon,
}: {
  label: string
  value: number
  tone?: 'live'
  icon?: typeof Users
}) {
  return (
    <div className="rounded-[var(--cd-radius-md)] border px-2 py-2 text-center" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}>
      <div className="flex items-center justify-center gap-1">
        {tone === 'live' && value > 0 ? (
          <CDStatusDot label={String(value)} tone="live" />
        ) : (
          <>
            {Icon && <Icon className="size-3" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />}
            <span className="font-[var(--cd-font-tabular)] text-[15px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
              {value}
            </span>
          </>
        )}
      </div>
      <p className="mt-0.5 truncate font-[var(--cd-font-telemetry)] text-[8.5px] font-medium uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
    </div>
  )
}
