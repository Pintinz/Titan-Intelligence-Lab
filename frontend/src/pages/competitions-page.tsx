import { useMemo, useState, type ReactNode } from 'react'
import { Trophy, Star, Activity } from 'lucide-react'
import { SPORT_SLUGS, type SportMeta } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useCompetitionIntelligence, type EnrichedCompetition } from '@/lib/hooks/use-competition-intelligence'
import { ErrorState } from '@/components/ui/error-state'
import { CompetitionHero } from '@/components/command-deck/competition-hero'
import { CompetitionCard } from '@/components/command-deck/competition-card'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { DomainKey } from '@/components/infinity/primitives/badge'

const FEATURED_LIMIT = 3
const RECENTLY_ACTIVE_LIMIT = 6

/** Wider breakpoints than the generic `MissionCardGrid` (which forces 3 columns at 1024px) —
 * these cards carry more content (crest, name, country/tier, 3-4 stat cells, teams-featured
 * line, AI badge + CTA) and truncate real competition names ("Premier League") at that density.
 * Holds 2 columns through the 1024-1279px range, 3 only from 1280px. */
function CompetitionGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/**
 * Competition Center — the cross-sport nav destination, redesigned per the shaped brief. Every
 * fixture count/team count/AI-ready flag traces to `useCompetitionIntelligence` (real fetched
 * data, no fabrication); Season is omitted entirely (no backend field exposes it yet), and
 * Featured is chosen by real `tier` data, not a hardcoded league-name list.
 */
export default function CompetitionsPage() {
  const [sport, setSport] = useState<SportMeta>(SPORT_SLUGS[0])
  const [search, setSearch] = useState('')
  const watchlist = useWatchlist()

  const { competitions, aiReady, isLoading, isError, error, refetch } = useCompetitionIntelligence(sport.code)
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

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

  function cardFor(competition: EnrichedCompetition, size?: 'featured' | 'default') {
    return (
      <CompetitionCard
        key={competition.id}
        competition={competition}
        href={`/app/${sport.slug}/competitions/${competition.id}`}
        sportDomain={domain}
        aiReady={aiReady}
        following={watchlist.isFollowing('competition', competition.id)}
        onToggleFollow={() => watchlist.toggle('competition', competition.id)}
        size={size}
      />
    )
  }

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
      <CompetitionHero sport={sport} onSportChange={setSport} search={search} onSearchChange={setSearch} backdropLogos={backdropLogos} />

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

          <MissionSection title={`${sport.label} Competitions`} subtitle={`Every ${sport.label} competition under TitanIQ coverage`} icon={<Trophy className="size-4" aria-hidden="true" />}>
            {competitions.length === 0 ? (
              <MissionEmptyState icon={Trophy} title="No competitions found" description={`No ${sport.label} competitions are under coverage yet.`} />
            ) : (
              <CompetitionGrid>{competitions.map((c) => cardFor(c))}</CompetitionGrid>
            )}
          </MissionSection>
        </>
      )}
    </div>
  )
}
