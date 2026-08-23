import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarX, CalendarClock } from 'lucide-react'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { useAvailableSports, useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureScores } from '@/lib/sports-status'
import { todayRange, tomorrowRange, thisWeekRange } from '@/lib/sports-date-ranges'
import { ErrorState } from '@/components/ui/error-state'
import { DiscoveryHero } from '@/components/command-deck/discovery/discovery-hero'
import { LiveRail } from '@/components/command-deck/discovery/live-rail'
import { TrendingIntelligence } from '@/components/command-deck/discovery/trending-intelligence'
import { RecentlyCompletedIntelligence } from '@/components/command-deck/discovery/recently-completed-intelligence'
import { CompetitionExplorer } from '@/components/command-deck/discovery/competition-explorer'
import { DiscoverySection } from '@/components/command-deck/discovery/discovery-section'
import { DiscoveryMatchCard } from '@/components/command-deck/discovery/discovery-match-card'
import type { FixtureSummaryDto } from '@/lib/api/types'
import type { MatchesScope } from './match-list-view-all-page'

export default function MatchListPage() {
  const sport = useSportParam()
  // Computed fresh on every render, not module scope — `todayRange()`/etc read `new Date()`, so a
  // module-level constant here would freeze "Today" at whatever moment this JS module first loaded
  // and never advance again for the life of the tab, including across a midnight rollover. That was
  // a real bug: a fixture dated yesterday would keep showing under "Today's matches" indefinitely.
  const SECTIONS: Array<{ scope: MatchesScope; title: string; range: { from: string; to: string } | null }> = [
    { scope: 'today', title: "Today's matches", range: todayRange() },
    { scope: 'tomorrow', title: 'Tomorrow', range: tomorrowRange() },
    { scope: 'week', title: 'This week', range: thisWeekRange() },
    { scope: 'completed', title: 'Completed', range: null },
  ]
  const availableSports = useAvailableSports()
  const navigate = useNavigate()
  const watchlist = useWatchlist()
  const [search, setSearch] = useState('')
  const [competitionId, setCompetitionId] = useState('')
  const [followingOnly, setFollowingOnly] = useState(false)

  const competitionsQuery = useQuery({
    queryKey: ['sports', sport?.code, 'competitions'],
    queryFn: () => sportsApi.listCompetitions(sport!.code),
    enabled: !!sport,
  })

  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
    staleTime: 5 * 60 * 1000,
  })
  const aiAvailable = (marketsQuery.data?.length ?? 0) > 0

  // Sport-wide KPI counts — always unfiltered by the competition selector, so the strip reads as
  // "the whole sport" while the sections below narrow with `competitionId`. Fetching real items
  // (not just a count) also feeds the Competition Explorer's real per-competition live counts.
  const liveCountQuery = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'discovery-kpi-live'],
    queryFn: () => sportsApi.listFixturesPaged(sport!.code, { status: 'live', limit: 50 }),
    enabled: !!sport,
    refetchInterval: 30_000,
  })
  const liveCountByCompetition = (liveCountQuery.data?.items ?? []).reduce<Record<string, number>>((acc, f) => {
    if (f.competition_id) acc[f.competition_id] = (acc[f.competition_id] ?? 0) + 1
    return acc
  }, {})
  const todayCountQuery = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'discovery-kpi-today'],
    queryFn: () => sportsApi.listFixturesPaged(sport!.code, { date_from: todayRange().from, date_to: todayRange().to, limit: 1 }),
    enabled: !!sport,
  })
  // Also feeds the Competition Explorer's real per-competition counts — one shared fetch, not
  // one query per chip.
  const thisWeekQuery = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'discovery-kpi-week'],
    queryFn: () => sportsApi.listFixturesPaged(sport!.code, { date_from: thisWeekRange().from, date_to: thisWeekRange().to, limit: 100 }),
    enabled: !!sport,
  })
  const fixtureCountByCompetition = (thisWeekQuery.data?.items ?? []).reduce<Record<string, number>>((acc, f) => {
    if (f.competition_id) acc[f.competition_id] = (acc[f.competition_id] ?? 0) + 1
    return acc
  }, {})

  const trimmedSearch = search.trim()
  const searchQuery = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'matches-search', trimmedSearch, competitionId],
    queryFn: () =>
      sportsApi.listFixturesPaged(sport!.code, {
        search: trimmedSearch || undefined,
        competition_id: competitionId || undefined,
        limit: 24,
      }),
    enabled: !!sport && trimmedSearch.length > 0,
  })

  // Today/Tomorrow/This week together span the next 7 days — when nothing at all falls in that
  // window (a real gap in coverage, not a bug), fall back to whatever's soonest instead of
  // showing three empty boxes in a row.
  const nearTermFrom = todayRange().from
  const nearTermTo = thisWeekRange().to
  const nearTermQuery = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'matches-near-term-check', nearTermFrom, nearTermTo, competitionId],
    queryFn: () =>
      sportsApi.listFixturesPaged(sport!.code, {
        date_from: nearTermFrom,
        date_to: nearTermTo,
        competition_id: competitionId || undefined,
        limit: 1,
      }),
    enabled: !!sport,
  })
  const showUpcomingFallback = !nearTermQuery.isPending && (nearTermQuery.data?.total ?? 0) === 0

  if (!sport) return null
  const isSearching = trimmedSearch.length > 0

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <DiscoveryHero
        sport={sport}
        search={search}
        onSearchChange={setSearch}
        followingOnly={followingOnly}
        onToggleFollowingOnly={() => setFollowingOnly((v) => !v)}
        kpis={{
          live: liveCountQuery.data?.total ?? null,
          today: todayCountQuery.data?.total ?? null,
          thisWeek: thisWeekQuery.data?.total ?? null,
          aiMarkets: marketsQuery.data?.length ?? null,
          competitions: competitionsQuery.data?.length ?? null,
        }}
      />

      <div className="flex flex-wrap gap-1.5">
        {availableSports.map((opt) => (
          <button
            key={opt.code}
            type="button"
            onClick={() => opt.code !== sport.code && navigate(`/app/${slugFor(opt.code)}/matches`)}
            className="rounded-full border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
            style={
              opt.code === sport.code
                ? { borderColor: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)', color: 'var(--cd-accent)' }
                : { borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-secondary)' }
            }
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isSearching ? (
        <SearchResults
          sportSlug={sport.slug}
          isPending={searchQuery.isPending}
          isError={searchQuery.isError}
          error={searchQuery.error}
          items={searchQuery.data?.items ?? []}
          aiAvailable={aiAvailable}
          following={watchlist.isFollowing}
          onToggleFollow={watchlist.toggle}
          onRetry={() => void searchQuery.refetch()}
        />
      ) : (
        <div className="space-y-8">
          <LiveRail sportSlug={sport.slug} sportCode={sport.code} competitionId={competitionId} aiAvailable={aiAvailable} followingOnly={followingOnly} />

          <TrendingIntelligence sportSlug={sport.slug} sportCode={sport.code} />

          <CompetitionExplorer
            competitions={competitionsQuery.data ?? []}
            fixtureCountByCompetition={fixtureCountByCompetition}
            liveCountByCompetition={liveCountByCompetition}
            selectedId={competitionId}
            onSelect={setCompetitionId}
          />

          {showUpcomingFallback && (
            <UpcomingFallbackSection
              sportSlug={sport.slug}
              sportCode={sport.code}
              competitionId={competitionId}
              aiAvailable={aiAvailable}
              followingOnly={followingOnly}
              watchlist={watchlist}
            />
          )}

          {SECTIONS.map((section) => (
            <DiscoverySection
              key={section.scope}
              sportSlug={sport.slug}
              sportCode={sport.code}
              scope={section.scope}
              title={section.title}
              range={section.range}
              competitionId={competitionId}
              aiAvailable={aiAvailable}
              followingOnly={followingOnly}
            />
          ))}

          <RecentlyCompletedIntelligence sportSlug={sport.slug} sportCode={sport.code} />
        </div>
      )}
    </div>
  )
}

function slugFor(code: SportCode): string {
  return code.replace('_', '-')
}

function SearchResults({
  sportSlug,
  isPending,
  isError,
  error,
  items,
  aiAvailable,
  following,
  onToggleFollow,
  onRetry,
}: {
  sportSlug: string
  isPending: boolean
  isError: boolean
  error: unknown
  items: FixtureSummaryDto[]
  aiAvailable: boolean
  following: (type: 'fixture', ref: string) => boolean
  onToggleFollow: (type: 'fixture', ref: string) => void
  onRetry: () => void
}) {
  if (isPending) {
    return (
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
        ))}
      </div>
    )
  }
  if (isError) return <ErrorState error={error} onRetry={onRetry} />
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-[var(--cd-radius-lg)] border border-dashed px-4 py-10 text-center" style={{ borderColor: 'var(--cd-border-default)' }}>
        <CalendarX className="size-5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <p className="font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          No matches found
        </p>
        <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          Try a different team or competition name.
        </p>
      </div>
    )
  }
  return (
    <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((fixture) => {
        const { homeScore, awayScore } = fixtureScores(fixture.final_state)
        const status = fixture.status.toLowerCase() === 'completed' ? 'completed' : fixture.status.toLowerCase() === 'live' ? 'live' : 'upcoming'
        return (
          <DiscoveryMatchCard
            key={fixture.id}
            competition={fixture.competition_name}
            competitionLogoUrl={fixture.competition_logo_url}
            status={status}
            kickoffLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
            venue={fixture.venue_name}
            homeTeam={fixture.home_team.name}
            awayTeam={fixture.away_team.name}
            homeScore={homeScore}
            awayScore={awayScore}
            homeLogoUrl={fixture.home_team.logo_url}
            awayLogoUrl={fixture.away_team.logo_url}
            aiAvailable={aiAvailable}
            following={following('fixture', fixture.id)}
            onToggleFollow={() => onToggleFollow('fixture', fixture.id)}
            href={status === 'completed' ? `/app/${sportSlug}/matches/${fixture.id}/review` : `/app/${sportSlug}/matches/${fixture.id}`}
          />
        )
      })}
    </div>
  )
}

function UpcomingFallbackSection({
  sportSlug,
  sportCode,
  competitionId,
  aiAvailable,
  followingOnly,
  watchlist,
}: {
  sportSlug: string
  sportCode: SportCode
  competitionId: string
  aiAvailable: boolean
  followingOnly: boolean
  watchlist: ReturnType<typeof useWatchlist>
}) {
  const query = useQuery({
    queryKey: ['sports', sportCode, 'fixtures', 'matches-upcoming-fallback', competitionId],
    queryFn: () =>
      sportsApi.listFixturesPaged(sportCode, {
        status: 'scheduled',
        competition_id: competitionId || undefined,
        limit: 6,
      }),
  })
  const items = (query.data?.items ?? []).filter((f) => !followingOnly || watchlist.isFollowing('fixture', f.id))

  if (query.isPending || items.length === 0) return null

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <CalendarClock className="size-3.5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Upcoming
        </h3>
        <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          — nothing's scheduled in the next 7 days, so here's what's coming up next
        </span>
      </div>
      <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((fixture) => {
          const { homeScore, awayScore } = fixtureScores(fixture.final_state)
          return (
            <DiscoveryMatchCard
              key={fixture.id}
              competition={fixture.competition_name}
              competitionLogoUrl={fixture.competition_logo_url}
              status="upcoming"
              kickoffLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
              venue={fixture.venue_name}
              homeTeam={fixture.home_team.name}
              awayTeam={fixture.away_team.name}
              homeScore={homeScore}
              awayScore={awayScore}
              homeLogoUrl={fixture.home_team.logo_url}
              awayLogoUrl={fixture.away_team.logo_url}
              aiAvailable={aiAvailable}
              following={watchlist.isFollowing('fixture', fixture.id)}
              onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
              href={`/app/${sportSlug}/matches/${fixture.id}`}
            />
          )
        })}
      </div>
    </section>
  )
}
