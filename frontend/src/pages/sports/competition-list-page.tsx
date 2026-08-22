import { useMemo, useState, type ReactNode } from 'react'
import { Trophy, Star, Activity } from 'lucide-react'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useCompetitionIntelligence, type EnrichedCompetition } from '@/lib/hooks/use-competition-intelligence'
import { ErrorState } from '@/components/ui/error-state'
import { CompetitionHero } from '@/components/command-deck/competition-hero'
import { CompetitionCard } from '@/components/command-deck/competition-card'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { DomainKey } from '@/components/infinity/primitives/badge'

const FEATURED_LIMIT = 3
const RECENTLY_ACTIVE_LIMIT = 6

/** Same wider breakpoints as Competition Intelligence's cross-sport grid — these cards carry
 * crest, name, country/tier, stat cells, teams-featured line, AI badge and a CTA, and truncate
 * real competition names at the generic grid's 1024px 3-column density. */
function CompetitionGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/**
 * Sport-scoped Competition Intelligence — the same Command Deck treatment as the cross-sport
 * `/app/competitions` page (`competitions-page.tsx`), applied inside a Sport Intelligence Center
 * where the sport is already fixed by the route and `SportShell`'s own tab bar, not re-selected
 * here. `CompetitionHero` renders without `onSportChange` so its segmented control stays hidden.
 */
export default function CompetitionListPage() {
  const sport = useSportParam()
  const [search, setSearch] = useState('')
  const watchlist = useWatchlist()

  const { competitions, aiReady, isLoading, isError, error, refetch } = useCompetitionIntelligence(sport?.code ?? 'football')
  const domain = (sport?.slug ?? 'football') as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  const backdropLogos = useMemo(() => competitions.map((c) => c.logo_url).filter((u): u is string => !!u), [competitions])

  const searching = search.trim().length > 0
  const searchResults = useMemo(() => {
    if (!searching) return []
    const q = search.trim().toLowerCase()
    return competitions.filter((c) => c.name.toLowerCase().includes(q) || (c.country ?? '').toLowerCase().includes(q))
  }, [competitions, search, searching])

  const featured = useMemo(
    () =>
      competitions
        .filter((c) => c.tier === 1)
        .sort((a, b) => b.liveCount + b.upcomingCount - (a.liveCount + a.upcomingCount))
        .slice(0, FEATURED_LIMIT),
    [competitions],
  )
  const featuredIds = useMemo(() => new Set(featured.map((c) => c.id)), [featured])

  const recentlyActive = useMemo(
    () =>
      competitions
        .filter((c) => !featuredIds.has(c.id) && c.liveCount + c.upcomingCount + c.completedCount > 0)
        .sort((a, b) => b.liveCount - a.liveCount || b.upcomingCount - a.upcomingCount || b.completedCount - a.completedCount)
        .slice(0, RECENTLY_ACTIVE_LIMIT),
    [competitions, featuredIds],
  )

  // A competition with zero live/upcoming/completed fixtures is a card with nothing to show —
  // usually a duplicate entity from a second provider that never had fixtures reconciled onto it,
  // rather than a real gap in coverage. Search still reaches every competition by name; only this
  // browse grid hides the dead ones.
  const competitionsWithActivity = useMemo(
    () => competitions.filter((c) => c.liveCount + c.upcomingCount + c.completedCount > 0),
    [competitions],
  )

  if (!sport) return null

  function cardFor(competition: EnrichedCompetition, size?: 'featured' | 'default') {
    return (
      <CompetitionCard
        key={competition.id}
        competition={competition}
        href={`/app/${sport!.slug}/competitions/${competition.id}`}
        sportDomain={domain}
        aiReady={aiReady}
        following={watchlist.isFollowing('competition', competition.id)}
        onToggleFollow={() => watchlist.toggle('competition', competition.id)}
        size={size}
      />
    )
  }

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <CompetitionHero sport={sport} search={search} onSearchChange={setSearch} backdropLogos={backdropLogos} />

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isError && isLoading && <MissionSkeletonGrid count={6} />}

      {!isError && !isLoading && searching && (
        <MissionSection title={`Results for "${search.trim()}"`} subtitle={`${searchResults.length} competition${searchResults.length === 1 ? '' : 's'} matched`}>
          {searchResults.length === 0 ? (
            <MissionEmptyState icon={Trophy} title="No competitions matched" description={`Nothing in ${sport.label} matches "${search.trim()}" — try a different search.`} />
          ) : (
            <CompetitionGrid>{searchResults.map((c) => cardFor(c))}</CompetitionGrid>
          )}
        </MissionSection>
      )}

      {!isError && !isLoading && !searching && (
        <>
          {featured.length > 0 && (
            <MissionSection title="Featured Competitions" subtitle="Top-flight coverage, ranked by current activity" icon={<Star className="size-4" aria-hidden="true" />} domain={domain}>
              <CompetitionGrid>{featured.map((c) => cardFor(c, 'featured'))}</CompetitionGrid>
            </MissionSection>
          )}

          {recentlyActive.length > 0 && (
            <MissionSection title="Recently Active" subtitle="Competitions with live, upcoming or completed fixtures right now" icon={<Activity className="size-4" aria-hidden="true" />}>
              <CompetitionGrid>{recentlyActive.map((c) => cardFor(c))}</CompetitionGrid>
            </MissionSection>
          )}

          <MissionSection title={`${sport.label} Competitions`} subtitle={`Every ${sport.label} competition with a live, upcoming or completed fixture`} icon={<Trophy className="size-4" aria-hidden="true" />}>
            {competitionsWithActivity.length === 0 ? (
              <MissionEmptyState icon={Trophy} title="No competitions found" description={`No ${sport.label} competitions are under coverage yet.`} />
            ) : (
              <CompetitionGrid>{competitionsWithActivity.map((c) => cardFor(c))}</CompetitionGrid>
            )}
          </MissionSection>
        </>
      )}
    </div>
  )
}
