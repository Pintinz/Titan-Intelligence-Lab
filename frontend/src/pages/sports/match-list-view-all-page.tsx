import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarX, Star } from 'lucide-react'
import { sportsApi, type FixtureQueryOpts } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { todayRange, tomorrowRange, thisWeekRange } from '@/lib/sports-date-ranges'
import { cn } from '@/lib/cn'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinitySearchInput } from '@/components/infinity/primitives/input'
import { InfinityButton } from '@/components/infinity/primitives/button'
import type { DomainKey } from '@/components/infinity/primitives/badge'

export type MatchesScope = 'today' | 'tomorrow' | 'week' | 'completed'

const SCOPE_META: Record<MatchesScope, { title: string; description: string }> = {
  today: { title: "Today's matches", description: 'Every match kicking off today.' },
  tomorrow: { title: "Tomorrow's matches", description: 'Every match scheduled for tomorrow.' },
  week: { title: 'This week', description: 'Matches scheduled over the rest of this week.' },
  completed: { title: 'Completed matches', description: 'Recently finished matches, most recent first.' },
}

const PAGE_SIZE = 24

function dateOptsFor(scope: MatchesScope): { date_from?: string; date_to?: string } {
  if (scope === 'today') {
    const r = todayRange()
    return { date_from: r.from, date_to: r.to }
  }
  if (scope === 'tomorrow') {
    const r = tomorrowRange()
    return { date_from: r.from, date_to: r.to }
  }
  if (scope === 'week') {
    const r = thisWeekRange()
    return { date_from: r.from, date_to: r.to }
  }
  return {}
}

/** The shared "View All" destination for every Matches section — one paginated, filterable list
 * component parameterized by `scope` instead of four near-identical pages. */
export default function MatchListViewAllPage({ scope }: { scope: MatchesScope }) {
  const sport = useSportParam()
  const watchlist = useWatchlist()
  const [search, setSearch] = useState('')
  const [competitionId, setCompetitionId] = useState<string>('')
  const [seasonId, setSeasonId] = useState<string>('')
  const [followingOnly, setFollowingOnly] = useState(false)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  const competitionsQuery = useQuery({
    queryKey: ['sports', sport?.code, 'competitions'],
    queryFn: () => sportsApi.listCompetitions(sport!.code),
    enabled: !!sport,
  })

  const seasonsQuery = useQuery({
    queryKey: ['sports', 'competitions', competitionId, 'seasons'],
    queryFn: () => sportsApi.competitionSeasons(competitionId),
    enabled: scope === 'completed' && !!competitionId,
  })

  // Deliberately not memoized: `dateOptsFor` reads `new Date()`, so caching this against
  // [scope, competitionId, seasonId, search] alone would freeze the Today/Tomorrow/This week
  // window at whatever moment the page first mounted for as long as it stays mounted, the same
  // staleness bug this object shape had on `match-list-page.tsx`'s "Today's matches" section.
  // `baseOpts` only ever feeds a `useQuery` queryKey, which is content-hashed — a fresh object with
  // the same values costs nothing extra.
  const baseOpts: FixtureQueryOpts = {
    ...dateOptsFor(scope),
    ...(scope === 'completed' ? { status: 'completed' as const } : {}),
    ...(competitionId ? { competition_id: competitionId } : {}),
    ...(scope === 'completed' && seasonId ? { season_id: seasonId } : {}),
    ...(search.trim() ? { search: search.trim() } : {}),
  }

  const query = useQuery({
    queryKey: ['sports', sport?.code, 'fixtures', 'view-all', scope, baseOpts, visibleCount],
    queryFn: () => sportsApi.listFixturesPaged(sport!.code, { ...baseOpts, limit: visibleCount, offset: 0 }),
    enabled: !!sport,
  })

  const seasons = seasonsQuery.data ?? []

  const items = (query.data?.items ?? []).filter(
    (f) => !followingOnly || watchlist.isFollowing('fixture', f.id),
  )
  const hasMore = (query.data?.hasMore ?? false) && !followingOnly

  // Real actual-vs-predicted accuracy per completed fixture, bounded to the currently-loaded page
  // (same accepted per-page fan-out pattern discovery-section.tsx already uses for match
  // statistics) — never a second, client-computed accuracy figure, always the same
  // `predictionsApi.review()` meta the Match Review page itself reads.
  const reviewQueries = useQueries({
    queries:
      scope === 'completed'
        ? items.map((fixture) => ({
            queryKey: ['predictions', 'review', fixture.id],
            queryFn: () => predictionsApi.review(fixture.id),
            staleTime: 5 * 60 * 1000,
          }))
        : [],
  })
  const loadedReviews = reviewQueries.filter((q) => q.data).map((q) => q.data!)
  const pageAccuracy =
    scope === 'completed' && loadedReviews.length > 0
      ? {
          resolved: loadedReviews.reduce((sum, r) => sum + r.meta.resolved_count, 0),
          correct: loadedReviews.reduce((sum, r) => sum + r.meta.correct_count, 0),
        }
      : null

  if (!sport) return null

  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  const meta = SCOPE_META[scope]

  return (
    <div className="space-y-6">
      <div>
        <Link
          to={`/app/${sport.slug}/matches`}
          className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
        >
          <ArrowLeft className="size-3.5" /> Back to matches
        </Link>
        <InfinityLabel tone="var(--infinity-signal)" className="mt-3 block">
          {sport.label}
        </InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">{meta.title}</h2>
        <p className="mt-0.5 font-infinity-body text-[13px] text-infinity-text-secondary">{meta.description}</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="w-full max-w-xs">
          <InfinitySearchInput
            placeholder="Search team or competition"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setVisibleCount(PAGE_SIZE)
            }}
          />
        </div>
        <select
          value={competitionId}
          onChange={(e) => {
            setCompetitionId(e.target.value)
            setSeasonId('')
            setVisibleCount(PAGE_SIZE)
          }}
          className="h-9 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 px-3 font-infinity-body text-[13px] text-infinity-text-primary focus:border-infinity-signal focus:outline-none focus:ring-1 focus:ring-infinity-signal"
        >
          {/* Native <option> ignores the <select>'s own background/text classes in its dropdown
              popup — Chrome/Firefox both default it to a white background, so without repeating
              the color classes here the light theme text renders unreadable on that white popup. */}
          <option value="" className="bg-infinity-ground-0 text-infinity-text-primary">All competitions</option>
          {(competitionsQuery.data ?? []).map((c) => (
            <option key={c.id} value={c.id} className="bg-infinity-ground-0 text-infinity-text-primary">
              {c.name}
            </option>
          ))}
        </select>
        {scope === 'completed' && competitionId && seasons.length > 0 && (
          <select
            value={seasonId}
            onChange={(e) => {
              setSeasonId(e.target.value)
              setVisibleCount(PAGE_SIZE)
            }}
            className="h-9 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 px-3 font-infinity-body text-[13px] text-infinity-text-primary focus:border-infinity-signal focus:outline-none focus:ring-1 focus:ring-infinity-signal"
          >
            <option value="" className="bg-infinity-ground-0 text-infinity-text-primary">Every season</option>
            {seasons.map((s) => (
              <option key={s.id} value={s.id} className="bg-infinity-ground-0 text-infinity-text-primary">
                {s.label} season
              </option>
            ))}
          </select>
        )}
        <button
          type="button"
          onClick={() => setFollowingOnly((v) => !v)}
          className={cn(
            'inline-flex h-9 items-center gap-1.5 rounded-infinity-sm border px-3 font-infinity-body text-[13px] font-medium transition-colors',
            followingOnly
              ? 'border-infinity-warning bg-infinity-warning/10 text-infinity-warning'
              : 'border-infinity-border-default text-infinity-text-secondary hover:text-infinity-text-primary',
          )}
        >
          <Star className="size-3.5" fill={followingOnly ? 'currentColor' : 'none'} aria-hidden="true" />
          Following
        </button>
      </div>

      {query.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}

      {!query.isPending && !query.isError && items.length === 0 && (
        <InfinityEmptyState
          icon={CalendarX}
          title="No matches found"
          description="Nothing matches these filters right now — try widening your search."
        />
      )}

      {scope === 'completed' && pageAccuracy && pageAccuracy.resolved > 0 && (
        <p className="font-infinity-mono text-[11px] text-infinity-text-muted">
          Across the {loadedReviews.length} loaded match{loadedReviews.length === 1 ? '' : 'es'} with resolved predictions:{' '}
          <span className="font-semibold text-infinity-text-secondary">
            {pageAccuracy.correct}/{pageAccuracy.resolved} correct ({Math.round((pageAccuracy.correct / pageAccuracy.resolved) * 100)}%)
          </span>
        </p>
      )}

      {items.length > 0 && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((fixture, i) => {
              const { homeScore, awayScore } = fixtureScores(fixture.final_state)
              const status = fixtureCardStatus(fixture.status)
              return (
                <InfinityMatchCard
                  key={fixture.id}
                  sport={domain}
                  competition={fixture.competition_name}
                  competitionLogoUrl={fixture.competition_logo_url}
                  status={status}
                  kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                  venue={fixture.venue_name}
                  homeTeam={fixture.home_team.name}
                  awayTeam={fixture.away_team.name}
                  homeScore={homeScore}
                  awayScore={awayScore}
                  homeLogoUrl={fixture.home_team.logo_url}
                  awayLogoUrl={fixture.away_team.logo_url}
                  stats={fixture.stats}
                  accuracy={scope === 'completed' ? reviewQueries[i]?.data?.meta : undefined}
                  following={watchlist.isFollowing('fixture', fixture.id)}
                  onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
                  href={status === 'completed' ? `/app/${sport.slug}/matches/${fixture.id}/review` : `/app/${sport.slug}/matches/${fixture.id}`}
                />
              )
            })}
          </div>
          {hasMore && (
            <div className="flex justify-center pt-2">
              <InfinityButton
                variant="secondary"
                onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                disabled={query.isFetching}
              >
                {query.isFetching ? 'Loading…' : 'Load more'}
              </InfinityButton>
            </div>
          )}
          {!hasMore && query.data && (
            <p className="text-center font-infinity-mono text-[11px] text-infinity-text-muted">
              {items.length} of {query.data.total} match{query.data.total === 1 ? '' : 'es'}
            </p>
          )}
        </>
      )}
    </div>
  )
}
