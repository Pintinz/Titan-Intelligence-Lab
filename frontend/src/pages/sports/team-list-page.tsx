import { useMemo, useState, type ReactNode } from 'react'
import { Trophy, Star, Users } from 'lucide-react'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useTeamIntelligence, type EnrichedTeam } from '@/lib/hooks/use-team-intelligence'
import { ErrorState } from '@/components/ui/error-state'
import { TeamHero } from '@/components/command-deck/team-hero'
import { TeamCard } from '@/components/command-deck/team-card'
import { CountryFilter } from '@/components/command-deck/country-filter'
import { TeamBrowseList } from '@/components/command-deck/team-browse-list'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { DomainKey } from '@/components/infinity/primitives/badge'

const FEATURED_LIMIT = 6

/** Same wider breakpoints as Team Intelligence's cross-sport grid — these cards carry crest,
 * name, league, country, AI badge and a CTA, and truncate real club names at the generic grid's
 * 1024px 3-column density. */
function TeamGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/**
 * Sport-scoped Team Intelligence — the same Command Deck treatment as the cross-sport
 * `/app/teams` page (`teams-page.tsx`), applied inside a Sport Intelligence Center where the
 * sport is already fixed by the route and `SportShell`'s own tab bar, not re-selected here.
 * `TeamHero` renders without `onSportChange` so its segmented control stays hidden.
 */
export default function TeamListPage() {
  const sport = useSportParam()
  const [search, setSearch] = useState('')
  const [country, setCountry] = useState<string | null>(null)
  const watchlist = useWatchlist()

  const { teams, aiReady, isLoading, isError, error, refetch } = useTeamIntelligence(sport?.code ?? 'football')
  const domain = (sport?.slug ?? 'football') as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  const backdropLogos = useMemo(() => teams.map((t) => t.logo_url).filter((u): u is string => !!u), [teams])

  const countryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const t of teams) {
      if (!t.country) continue
      counts.set(t.country, (counts.get(t.country) ?? 0) + 1)
    }
    return [...counts.entries()].sort(([, a], [, b]) => b - a).map(([c, count]) => ({ country: c, count }))
  }, [teams])

  const countryFiltered = useMemo(() => (country ? teams.filter((t) => t.country === country) : teams), [teams, country])

  const searching = search.trim().length > 0
  const searchResults = useMemo(() => {
    if (!searching) return []
    const q = search.trim().toLowerCase()
    return teams.filter(
      (t) => t.name.toLowerCase().includes(q) || (t.country ?? '').toLowerCase().includes(q) || (t.competitionName ?? '').toLowerCase().includes(q),
    )
  }, [teams, search, searching])

  const featured = useMemo(
    () =>
      teams
        .filter((t) => t.competitionTier === 1)
        .sort((a, b) => Number(b.liveNow) - Number(a.liveNow) || Number(!!b.nextFixtureId) - Number(!!a.nextFixtureId))
        .slice(0, FEATURED_LIMIT),
    [teams],
  )
  const featuredIds = useMemo(() => new Set(featured.map((t) => t.id)), [featured])
  const discoverTeams = useMemo(() => countryFiltered.filter((t) => !featuredIds.has(t.id)), [countryFiltered, featuredIds])

  if (!sport) return null

  function cardFor(team: EnrichedTeam, size?: 'featured' | 'default') {
    return (
      <TeamCard
        key={team.id}
        team={team}
        href={`/app/${sport!.slug}/teams/${team.id}`}
        generateHref={aiReady && team.nextFixtureId ? `/app/${sport!.slug}/matches/${team.nextFixtureId}` : null}
        sportDomain={domain}
        aiReady={aiReady}
        following={watchlist.isFollowing('team', team.id)}
        onToggleFollow={() => watchlist.toggle('team', team.id)}
        size={size}
      />
    )
  }

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <TeamHero sport={sport} search={search} onSearchChange={setSearch} backdropLogos={backdropLogos} />

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isError && isLoading && <MissionSkeletonGrid count={6} />}

      {!isError && !isLoading && searching && (
        <MissionSection title={`Results for "${search.trim()}"`} subtitle={`${searchResults.length} team${searchResults.length === 1 ? '' : 's'} matched`}>
          {searchResults.length === 0 ? (
            <MissionEmptyState
              icon={Users}
              title="TitanIQ is synchronizing team intelligence."
              description="Try a different search, or browse the sections below."
            />
          ) : (
            <TeamGrid>{searchResults.map((t) => cardFor(t))}</TeamGrid>
          )}
        </MissionSection>
      )}

      {!isError && !isLoading && !searching && (
        <>
          {featured.length > 0 && (
            <MissionSection title="Featured Teams" subtitle="Top-flight clubs, ranked by current activity" icon={<Star className="size-4" aria-hidden="true" />} domain={domain}>
              <TeamGrid>{featured.map((t) => cardFor(t, 'featured'))}</TeamGrid>
            </MissionSection>
          )}

          <MissionSection title="Discover Teams" subtitle={`Every ${sport.label} club under TitanIQ coverage`} icon={<Trophy className="size-4" aria-hidden="true" />}>
            {countryCounts.length > 0 && <div className="mb-4"><CountryFilter countryCounts={countryCounts} selected={country} onSelect={setCountry} sportDomain={domain} /></div>}
            {teams.length === 0 ? (
              <MissionEmptyState
                icon={Users}
                title="TitanIQ is synchronizing team intelligence."
                description={`${sport.label} coverage is still coming online.`}
              />
            ) : discoverTeams.length === 0 ? (
              <MissionEmptyState icon={Users} title="TitanIQ is synchronizing team intelligence." description="Try another country filter." />
            ) : (
              <TeamGrid>{discoverTeams.map((t) => cardFor(t))}</TeamGrid>
            )}
          </MissionSection>

          {teams.length > 0 && (
            <MissionSection title="Browse All Teams" subtitle={`All ${teams.length} ${sport.label} clubs, alphabetically`} icon={<Users className="size-4" aria-hidden="true" />}>
              <TeamBrowseList teams={countryFiltered} sportSlug={sport.slug} sportDomain={domain} />
            </MissionSection>
          )}
        </>
      )}
    </div>
  )
}
