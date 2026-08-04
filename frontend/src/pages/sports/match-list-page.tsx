import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarX, ChevronRight, CalendarClock } from 'lucide-react'
import { sportsApi, SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
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
import type { DomainKey } from '@/components/infinity/primitives/badge'
import type { FixtureSummaryDto } from '@/lib/api/types'
import type { MatchesScope } from './match-list-view-all-page'

const SECTIONS: Array<{ scope: MatchesScope; title: string }> = [
  { scope: 'today', title: "Today's matches" },
  { scope: 'tomorrow', title: 'Tomorrow' },
  { scope: 'week', title: 'This week' },
  { scope: 'completed', title: 'Completed' },
]

function dateOptsFor(scope: MatchesScope) {
  if (scope === 'today') return todayRange()
  if (scope === 'tomorrow') return tomorrowRange()
  if (scope === 'week') return thisWeekRange()
  return null
}

export default function MatchListPage() {
  const sport = useSportParam()
  const navigate = useNavigate()
  const watchlist = useWatchlist()
  const [search, setSearch] = useState('')
  const [competitionId, setCompetitionId] = useState('')

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
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  const isSearching = trimmedSearch.length > 0

  return (
    <div className="space-y-8">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Match Intelligence</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">{sport.label} matches</h2>
        <p className="mt-0.5 font-infinity-body text-[13px] text-infinity-text-secondary">
          TitanIQ's fixture discovery center — browse what's coming up and what's already been played.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5">
          {SPORT_OPTIONS.map((opt) => (
            <button
              key={opt.code}
              type="button"
              onClick={() => opt.code !== sport.code && navigate(`/app/${slugFor(opt.code)}/matches`)}
              className={cn(
                'rounded-infinity-full border px-3 py-1.5 font-infinity-body text-[12px] font-medium transition-colors',
                opt.code === sport.code
                  ? 'border-infinity-signal bg-infinity-signal-muted text-infinity-signal'
                  : 'border-infinity-border-hairline text-infinity-text-secondary hover:border-infinity-border-default hover:text-infinity-text-primary',
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="w-56">
            <InfinitySearchInput placeholder="Search team or competition" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <select
            value={competitionId}
            onChange={(e) => setCompetitionId(e.target.value)}
            className="h-9 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 px-3 font-infinity-body text-[13px] text-infinity-text-primary focus:border-infinity-signal focus:outline-none focus:ring-1 focus:ring-infinity-signal"
          >
            <option value="">All competitions</option>
            {(competitionsQuery.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {isSearching ? (
        <SearchResults
          domain={domain}
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
          {showUpcomingFallback && (
            <UpcomingFallbackSection
              sportSlug={sport.slug}
              sportCode={sport.code}
              domain={domain}
              competitionId={competitionId}
              aiAvailable={aiAvailable}
              watchlist={watchlist}
            />
          )}
          {SECTIONS.map((section) => (
            <MatchSection
              key={section.scope}
              sportSlug={sport.slug}
              sportCode={sport.code}
              domain={domain}
              scope={section.scope}
              title={section.title}
              competitionId={competitionId}
              aiAvailable={aiAvailable}
              watchlist={watchlist}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function slugFor(code: SportCode): string {
  return code.replace('_', '-')
}

function SearchResults({
  domain,
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
  domain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
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
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <InfinitySkeleton key={i} className="h-40" />
        ))}
      </div>
    )
  }
  if (isError) return <ErrorState error={error} onRetry={onRetry} />
  if (items.length === 0) {
    return <InfinityEmptyState icon={CalendarX} title="No matches found" description="Try a different team or competition name." />
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {items.map((fixture) => {
        const { homeScore, awayScore } = fixtureScores(fixture.final_state)
        return (
          <InfinityMatchCard
            key={fixture.id}
            sport={domain}
            competition={fixture.competition_name}
            competitionLogoUrl={fixture.competition_logo_url}
            status={fixtureCardStatus(fixture.status)}
            kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
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
            href={`/app/${sportSlug}/matches/${fixture.id}`}
          />
        )
      })}
    </div>
  )
}

function UpcomingFallbackSection({
  sportSlug,
  sportCode,
  domain,
  competitionId,
  aiAvailable,
  watchlist,
}: {
  sportSlug: string
  sportCode: SportCode
  domain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  competitionId: string
  aiAvailable: boolean
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
  const items = query.data?.items ?? []

  if (query.isPending || items.length === 0) return null

  return (
    <section>
      <div className="mb-3 flex items-center gap-2">
        <CalendarClock className="size-3.5 text-infinity-text-muted" aria-hidden="true" />
        <h3 className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">Upcoming</h3>
        <span className="font-infinity-body text-[12px] text-infinity-text-muted">
          — nothing's scheduled in the next 7 days, so here's what's coming up next
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((fixture) => {
          const { homeScore, awayScore } = fixtureScores(fixture.final_state)
          return (
            <InfinityMatchCard
              key={fixture.id}
              sport={domain}
              competition={fixture.competition_name}
              competitionLogoUrl={fixture.competition_logo_url}
              status={fixtureCardStatus(fixture.status)}
              kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
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

function MatchSection({
  sportSlug,
  sportCode,
  domain,
  scope,
  title,
  competitionId,
  aiAvailable,
  watchlist,
}: {
  sportSlug: string
  sportCode: SportCode
  domain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  scope: MatchesScope
  title: string
  competitionId: string
  aiAvailable: boolean
  watchlist: ReturnType<typeof useWatchlist>
}) {
  const range = dateOptsFor(scope)
  const query = useQuery({
    queryKey: ['sports', sportCode, 'fixtures', 'matches-section', scope, competitionId],
    queryFn: () =>
      sportsApi.listFixturesPaged(sportCode, {
        ...(range ? { date_from: range.from, date_to: range.to } : {}),
        ...(scope === 'completed' ? { status: 'completed' } : {}),
        competition_id: competitionId || undefined,
        limit: 6,
      }),
  })

  const items = query.data?.items ?? []

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-infinity-display text-[14px] font-semibold text-infinity-text-primary">{title}</h3>
        <Link
          to={`/app/${sportSlug}/matches/${scope}`}
          className="inline-flex items-center gap-0.5 font-infinity-body text-[12px] font-medium text-infinity-signal hover:text-infinity-signal-hover"
        >
          View all <ChevronRight className="size-3.5" aria-hidden="true" />
        </Link>
      </div>

      {query.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}

      {!query.isPending && !query.isError && items.length === 0 && (
        <p className="rounded-infinity-lg border border-dashed border-infinity-border-default px-4 py-6 text-center font-infinity-body text-[13px] text-infinity-text-muted">
          Nothing under coverage for this window yet.
        </p>
      )}

      {items.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((fixture) => {
            const { homeScore, awayScore } = fixtureScores(fixture.final_state)
            return (
              <InfinityMatchCard
                key={fixture.id}
                sport={domain}
                competition={fixture.competition_name}
                competitionLogoUrl={fixture.competition_logo_url}
                status={fixtureCardStatus(fixture.status)}
                kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
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
      )}
    </section>
  )
}
