import { Link } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Radar } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { CDStatusDot } from '../primitives/status'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import { CD_DOMAIN_COLOR_VAR, sportDomainFor } from '../primitives/domain'
import type { FixtureCardItem } from './live-intelligence'

/**
 * Competitions Under Watch — no cross-sport "competitions with live/upcoming counts" view exists
 * anywhere in the app yet (`/app/competitions` is a single-sport-at-a-time switcher with no
 * counts). This fetches each sport's real competition list (one query per sport, same pattern
 * this page already uses for Live/AI Ready) and derives live/upcoming counts from the fixtures
 * this page already fetched — no per-competition N+1 request.
 */
export function CompetitionsUnderWatch({
  liveFixtures,
  upcomingFixtures,
}: {
  liveFixtures: FixtureCardItem[]
  upcomingFixtures: FixtureCardItem[]
}) {
  const competitionQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'competitions', 'mission-control'],
      queryFn: () => sportsApi.listCompetitions(sport.code),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const isLoading = competitionQueries.some((q) => q.isPending)

  const liveCountByCompetition = countByCompetition(liveFixtures)
  const upcomingCountByCompetition = countByCompetition(upcomingFixtures)

  const competitions = SPORT_SLUGS.flatMap((sport, i) => (competitionQueries[i].data ?? []).map((c) => ({ competition: c, sport })))
    .sort((a, b) => (liveCountByCompetition[b.competition.id] ?? 0) - (liveCountByCompetition[a.competition.id] ?? 0))
    .slice(0, 6)

  return (
    <MissionSection
      id="competitions"
      title="Competitions Under Watch"
      subtitle="Coverage across every supported competition"
      icon={<Radar className="size-4" aria-hidden="true" />}
      viewAllHref="/app/competitions"
    >
      {isLoading && <MissionSkeletonGrid count={4} />}
      {!isLoading && competitions.length === 0 && (
        <MissionEmptyState icon={Radar} title="Building out coverage." description="TitanIQ is onboarding competitions across every supported sport." />
      )}
      {!isLoading && competitions.length > 0 && (
        <div className="-mx-1 flex snap-x gap-3.5 overflow-x-auto px-1 pb-1">
          {competitions.map(({ competition, sport }) => {
            const liveCount = liveCountByCompetition[competition.id] ?? 0
            const upcomingCount = upcomingCountByCompetition[competition.id] ?? 0
            const domain = sportDomainFor(sport.slug)
            return (
              <Link
                key={competition.id}
                to={`/app/${sport.slug}/competitions/${competition.id}`}
                className="group w-[204px] shrink-0 snap-start overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
                style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
              >
                <div className="flex items-center gap-2">
                  {competition.logo_url ? (
                    <img src={competition.logo_url} alt="" className="size-6 shrink-0 object-contain" loading="lazy" />
                  ) : (
                    <span
                      className="flex size-6 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[11px] font-semibold"
                      style={{ backgroundColor: domain ? `color-mix(in srgb, ${CD_DOMAIN_COLOR_VAR[domain]} 16%, var(--cd-surface-3))` : 'var(--cd-surface-3)', color: domain ? CD_DOMAIN_COLOR_VAR[domain] : 'var(--cd-text-muted)' }}
                    >
                      {competition.name.charAt(0).toUpperCase()}
                    </span>
                  )}
                  <p className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                    {competition.name}
                  </p>
                </div>
                <p
                  className="mt-1 flex items-center gap-1.5 font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.06em]"
                  style={{ color: domain ? CD_DOMAIN_COLOR_VAR[domain] : 'var(--cd-text-muted)' }}
                >
                  {domain && <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: CD_DOMAIN_COLOR_VAR[domain] }} aria-hidden="true" />}
                  {sport.label}
                </p>
                <div className="mt-3 flex items-center gap-3 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                  {liveCount > 0 ? (
                    <CDStatusDot label={`${liveCount} live`} tone="live" />
                  ) : (
                    <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                      {upcomingCount} upcoming
                    </span>
                  )}
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </MissionSection>
  )
}

function countByCompetition(items: FixtureCardItem[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const { fixture } of items) {
    if (!fixture.competition_id) continue
    counts[fixture.competition_id] = (counts[fixture.competition_id] ?? 0) + 1
  }
  return counts
}
