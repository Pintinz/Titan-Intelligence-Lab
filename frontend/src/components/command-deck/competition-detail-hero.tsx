import { Star, CalendarDays, Users } from 'lucide-react'
import { CDPanel } from './primitives/panel'
import { CDButton } from './primitives/button'
import { CDStatusDot } from './primitives/status'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from './primitives/domain'
import type { CompetitionSummaryDto } from '@/lib/api/types'

export type CompetitionStatus = 'active' | 'upcoming' | 'completed' | 'data-limited'

const STATUS_LABEL: Record<CompetitionStatus, string> = {
  active: 'Active',
  upcoming: 'Upcoming',
  completed: 'Completed',
  'data-limited': 'Data limited',
}

/**
 * CompetitionDetailHero — a compact operational header, not a marketing hero. Identity (crest,
 * name, country, sport·type) plus a real, derived status (never a fabricated "season state" —
 * `status` is computed by the page from the fixtures it already fetched: any live fixture reads
 * ACTIVE, any future one UPCOMING, all-past COMPLETED, none DATA LIMITED). Actions jump to the
 * page's own Fixtures/Teams tabs and toggle the real `competition` watchlist entity.
 */
export function CompetitionDetailHero({
  competition,
  sportLabel,
  sportDomain,
  status,
  following,
  onToggleFollow,
  onViewFixtures,
  onViewTeams,
}: {
  competition: CompetitionSummaryDto
  sportLabel: string
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  status: CompetitionStatus
  following: boolean
  onToggleFollow: () => void
  onViewFixtures: () => void
  onViewTeams: () => void
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const meta = [sportLabel, competition.type].filter(Boolean).join(' · ')

  return (
    <CDPanel className="relative overflow-hidden">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{ background: `radial-gradient(110% 90% at 0% 0%, ${domainTint(sportDomain, 16)}, transparent 60%)` }}
        aria-hidden="true"
      />

      <div className="relative flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <span
            className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-lg)] border"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)' }}
          >
            {competition.logo_url ? (
              <img src={competition.logo_url} alt="" className="size-9 object-contain" loading="lazy" />
            ) : (
              <span aria-hidden="true" className="font-[var(--cd-font-display)] text-xl font-semibold" style={{ color: domainColor }}>
                {competition.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <h1 className="font-[var(--cd-font-display)] text-[22px] font-semibold leading-tight sm:truncate sm:text-[26px]" style={{ color: 'var(--cd-text-primary)' }}>
              {competition.name}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
              {competition.country && (
                <span className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {competition.country}
                </span>
              )}
              {competition.country && meta && <span aria-hidden="true" style={{ color: 'var(--cd-text-muted)' }}>·</span>}
              {meta && (
                <span className="font-[var(--cd-font-telemetry)] text-[11px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  {meta}
                </span>
              )}
              <CDStatusDot label={STATUS_LABEL[status]} tone={status === 'active' ? 'live' : status === 'upcoming' ? 'ready' : 'idle'} />
            </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <CDButton variant="secondary" size="sm" onClick={onViewFixtures} icon={<CalendarDays className="size-3.5" aria-hidden="true" />}>
            View fixtures
          </CDButton>
          <CDButton variant="secondary" size="sm" onClick={onViewTeams} icon={<Users className="size-3.5" aria-hidden="true" />}>
            View teams
          </CDButton>
          <button
            type="button"
            onClick={onToggleFollow}
            aria-pressed={following}
            aria-label={following ? `Unfollow ${competition.name}` : `Follow ${competition.name}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-3 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
            style={{
              borderColor: following ? domainColor : 'var(--cd-border-default)',
              backgroundColor: following ? domainTint(sportDomain, 14) : 'transparent',
              color: following ? domainColor : 'var(--cd-text-secondary)',
            }}
          >
            <Star className="size-3.5" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
            {following ? 'Following' : 'Follow'}
          </button>
        </div>
      </div>
    </CDPanel>
  )
}
