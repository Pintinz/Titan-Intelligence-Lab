import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Radio, Trophy, Newspaper, Sparkles, Star, Gauge, Network, CalendarDays } from 'lucide-react'
import { sportsApi, SPORT_OPTIONS } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { intelligenceApi } from '@/lib/api/intelligence'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores, isLiveStatus } from '@/lib/sports-status'
import { todayRange } from '@/lib/sports-date-ranges'
import { useAuthStore } from '@/stores/auth-store'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel, InfinityPanel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinityPredictionCard } from '@/components/infinity/cards/prediction-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'
import type { FixtureSummaryDto } from '@/lib/api/types'

const SECTION_LIMIT = 6

/**
 * Home — Mission Control. A dashboard PREVIEW, not the full Matches/Live experience: every
 * section here caps at 6 cards and links out to the dedicated page via "View all". Every
 * section is real data already proven elsewhere in the app (Live, Matches, AI Picks, Watchlist,
 * News). Two sections use an honest derived substitute rather than a backend concept that
 * doesn't exist: "Trending Competitions" is competitions ranked by how many of today's fixtures
 * belong to them (a real, computable signal), not a popularity/view-count metric no backend
 * tracks; "Continue Watching" is the user's followed matches (real Watchlist data), not session
 * view-history, which nothing records.
 */
export default function HomePage() {
  const profile = useAuthStore((s) => s.profile)
  const watchlist = useWatchlist()

  const liveQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'live'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'live', limit: 50 }),
      refetchInterval: 30_000,
    })),
  })
  const todayRangeValue = todayRange()
  const todayQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'today', todayRangeValue.from],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { date_from: todayRangeValue.from, date_to: todayRangeValue.to, limit: 50 }),
    })),
  })
  const marketQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['markets', sport.code, 'production'],
      queryFn: () => marketsApi.list({ sport_code: sport.code, status: 'production' }),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const aiAvailableBySport = new Set(SPORT_SLUGS.filter((_, i) => (marketQueries[i].data?.length ?? 0) > 0).map((s) => s.code))

  const picksQuery = useQuery({ queryKey: ['predictions', 'picks', 'home'], queryFn: () => predictionsApi.picks({ limit: SECTION_LIMIT }) })
  const monitoringQuery = useQuery({ queryKey: ['predictions', 'monitoring', 'summary'], queryFn: () => predictionsApi.monitoringSummary() })
  const graphStatsQuery = useQuery({ queryKey: ['graph', 'statistics'], queryFn: () => graphApi.statistics() })
  const newsQuery = useQuery({ queryKey: ['intelligence', 'news', 'home'], queryFn: () => intelligenceApi.searchNews({ limit: SECTION_LIMIT }) })

  const anyLiveLoading = liveQueries.some((q) => q.isPending)
  const anyTodayLoading = todayQueries.some((q) => q.isPending)

  const liveWithSport = SPORT_SLUGS.flatMap((sport, i) => (liveQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })))
  const todayWithSport = SPORT_SLUGS.flatMap((sport, i) => (todayQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })))
  const todayNonLive = todayWithSport.filter((x) => !isLiveStatus(x.fixture.status))

  // Nothing today is a real coverage gap, not a bug (dev/early-coverage data can start weeks
  // out) — once we know for sure, fall back to whatever's soonest instead of an empty section.
  const todayIsEmpty = !anyTodayLoading && todayNonLive.length === 0
  const upcomingFallbackQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'upcoming-fallback'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'scheduled', limit: 6 }),
      enabled: todayIsEmpty,
    })),
  })
  const anyFallbackLoading = todayIsEmpty && upcomingFallbackQueries.some((q) => q.isPending)
  const upcomingFallbackWithSport = SPORT_SLUGS.flatMap((sport, i) =>
    (upcomingFallbackQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })),
  )
  const showUpcomingFallback = todayIsEmpty && !anyFallbackLoading && upcomingFallbackWithSport.length > 0

  const liveCount = liveQueries.reduce((sum, q) => sum + (q.data?.total ?? 0), 0)
  const todayCount = todayQueries.reduce((sum, q) => sum + (q.data?.total ?? 0), 0)

  const trendingCompetitions = rankCompetitionsByActivity(todayWithSport.map((x) => x.fixture)).slice(0, 4)

  const watchedFixtureIds = (watchlist.data ?? []).filter((e) => e.entity_type === 'fixture').map((e) => e.entity_ref)
  const continueWatchingQueries = useQueries({
    queries: watchedFixtureIds.slice(0, SECTION_LIMIT).map((id) => ({
      queryKey: ['sports', 'fixtures', id],
      queryFn: () => sportsApi.getFixture(id),
    })),
  })

  const firstName = profile?.email?.split('@')[0]

  return (
    <div className="space-y-10">
      {/* Hero — real aggregate intelligence telemetry, never marketing copy. */}
      <InfinityPanel tone="var(--infinity-signal)" glow>
        <InfinityLabel tone="var(--infinity-signal)">Mission Control</InfinityLabel>
        <h1 className="mt-1 font-infinity-display text-xl font-semibold text-infinity-text-primary">
          {firstName ? `Welcome back, ${firstName}` : 'Welcome back'}
        </h1>
        <p className="mt-1 font-infinity-body text-[13px] text-infinity-text-secondary">
          Everything TitanIQ is tracking right now, across every sport.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <HeroStat icon={Radio} label="Live now" value={anyLiveLoading ? undefined : liveCount} live={liveCount > 0} />
          <HeroStat icon={CalendarDays} label="Matches today" value={anyTodayLoading ? undefined : todayCount} />
          <HeroStat
            icon={Gauge}
            label="Predictions tracked"
            value={monitoringQuery.isPending ? undefined : (monitoringQuery.data?.sample_size as number | undefined) ?? 0}
          />
          <HeroStat
            icon={Network}
            label="Knowledge Graph nodes"
            value={graphStatsQuery.isPending ? undefined : (graphStatsQuery.data?.node_count as number | undefined) ?? 0}
          />
        </div>
      </InfinityPanel>

      {/* Live Now — a preview of /app/live, capped at 6, never mixed with non-live fixtures. */}
      <Section icon={Radio} title="Live now" viewAllHref="/app/live" tone="var(--infinity-live)">
        {anyLiveLoading && <SkeletonRow count={3} tall />}
        {!anyLiveLoading && liveWithSport.length === 0 && (
          <InfinityEmptyState icon={Radio} title="No live matches at the moment" description="Upcoming matches begin soon." />
        )}
        {liveWithSport.length > 0 && (
          <CardGrid>
            {sortByKickoff(liveWithSport)
              .slice(0, SECTION_LIMIT)
              .map(({ fixture, sport }) => (
                <FixtureCard
                  key={fixture.id}
                  fixture={fixture}
                  sportSlug={sport.slug}
                  aiAvailable={aiAvailableBySport.has(sport.code)}
                  watchlist={watchlist}
                />
              ))}
          </CardGrid>
        )}
      </Section>

      {/* Today's Matches — a preview of /app/:sport/matches's Today section, live matches excluded
          (they already have their own section above). Falls back to the soonest upcoming
          matches when nothing's scheduled today, same as the Matches page. */}
      <Section
        icon={CalendarDays}
        title={showUpcomingFallback ? 'Upcoming' : "Today's matches"}
        viewAllHref={showUpcomingFallback ? `/app/${SPORT_SLUGS[0].slug}/matches` : `/app/${SPORT_SLUGS[0].slug}/matches/today`}
      >
        {(anyTodayLoading || anyFallbackLoading) && <SkeletonRow count={3} />}
        {!anyTodayLoading && !anyFallbackLoading && todayNonLive.length === 0 && upcomingFallbackWithSport.length === 0 && (
          <InfinityEmptyState icon={CalendarDays} title="Nothing scheduled today" description="Check back tomorrow, or browse the full schedule." />
        )}
        {todayNonLive.length > 0 && (
          <CardGrid>
            {sortByKickoff(todayNonLive)
              .slice(0, SECTION_LIMIT)
              .map(({ fixture, sport }) => (
                <FixtureCard
                  key={fixture.id}
                  fixture={fixture}
                  sportSlug={sport.slug}
                  aiAvailable={aiAvailableBySport.has(sport.code)}
                  watchlist={watchlist}
                />
              ))}
          </CardGrid>
        )}
        {showUpcomingFallback && (
          <>
            <p className="mb-3 font-infinity-body text-[12px] text-infinity-text-muted">
              Nothing's scheduled today — here's what's coming up next.
            </p>
            <CardGrid>
              {sortByKickoff(upcomingFallbackWithSport)
                .slice(0, SECTION_LIMIT)
                .map(({ fixture, sport }) => (
                  <FixtureCard
                    key={fixture.id}
                    fixture={fixture}
                    sportSlug={sport.slug}
                    aiAvailable={aiAvailableBySport.has(sport.code)}
                    watchlist={watchlist}
                  />
                ))}
            </CardGrid>
          </>
        )}
      </Section>

      {/* Trending Competitions */}
      <Section icon={Trophy} title="Trending competitions" viewAllHref="/app/competitions">
        {anyTodayLoading && <SkeletonRow count={4} />}
        {!anyTodayLoading && trendingCompetitions.length === 0 && (
          <InfinityEmptyState icon={Trophy} title="No competitions active" description="Nothing under coverage right now." />
        )}
        {trendingCompetitions.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {trendingCompetitions.map((c) => (
              <div key={c.name} className="rounded-infinity-md border border-infinity-border-hairline p-3">
                <p className="truncate font-infinity-body text-[13px] font-medium text-infinity-text-primary">{c.name}</p>
                <p className="mt-1 font-infinity-mono text-[11px] text-infinity-text-muted">{c.count} matches today</p>
              </div>
            ))}
          </div>
        )}
      </Section>

      {/* AI Picks */}
      <Section icon={Sparkles} title="AI Picks" viewAllHref="/app/picks" tone="var(--infinity-domain-predictions)">
        {picksQuery.isPending && <SkeletonRow count={3} tall />}
        {picksQuery.isError && <ErrorState error={picksQuery.error} onRetry={() => void picksQuery.refetch()} />}
        {picksQuery.data && picksQuery.data.length === 0 && (
          <InfinityEmptyState icon={Sparkles} title="No AI Picks yet" description="Picks appear once TitanIQ has published high-confidence predictions." />
        )}
        {picksQuery.data && picksQuery.data.length > 0 && (
          <CardGrid>
            {picksQuery.data.map((pick) => (
              <InfinityPredictionCard
                key={pick.id}
                market={pick.market_name}
                selection={String(pick.value)}
                probability={pick.probability}
                confidence={pick.confidence_composite}
                evidenceCount={pick.evidence_count}
              />
            ))}
          </CardGrid>
        )}
      </Section>

      {/* Breaking Intelligence */}
      <Section icon={Newspaper} title="Breaking intelligence" viewAllHref="/app/news">
        {newsQuery.isPending && <SkeletonRow count={4} short />}
        {newsQuery.isError && <ErrorState error={newsQuery.error} onRetry={() => void newsQuery.refetch()} />}
        {newsQuery.data && newsQuery.data.length === 0 && (
          <InfinityEmptyState icon={Newspaper} title="No news yet" description="Nothing has synced from a news source yet." />
        )}
        {newsQuery.data && newsQuery.data.length > 0 && (
          <ul className="space-y-2">
            {newsQuery.data.map((article) => (
              <li key={article.id} className="rounded-infinity-md border border-infinity-border-hairline p-3">
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-infinity-body text-[13px] font-medium text-infinity-text-primary hover:text-infinity-signal"
                >
                  {article.title}
                </a>
                <p className="mt-1 font-infinity-mono text-[10px] text-infinity-text-muted">
                  {new Date(article.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Continue Watching — the user's followed matches, real Watchlist data. */}
      <Section icon={Star} title="Continue watching" viewAllHref="/app/watchlist">
        {watchlist.isPending && <SkeletonRow count={3} />}
        {!watchlist.isPending && watchedFixtureIds.length === 0 && (
          <InfinityEmptyState icon={Star} title="Nothing followed yet" description="Follow a match from its card to track it here." />
        )}
        {watchedFixtureIds.length > 0 && (
          <CardGrid>
            {continueWatchingQueries.map((q, i) => {
              if (q.isPending) return <InfinitySkeleton key={watchedFixtureIds[i]} className="h-40" />
              if (q.isError || !q.data) return null
              const fixture = q.data
              const sportSlug = (fixture.sport_code ?? 'football').replace('_', '-')
              return (
                <FixtureCard
                  key={fixture.id}
                  fixture={fixture}
                  sportSlug={sportSlug}
                  aiAvailable={aiAvailableBySport.has((fixture.sport_code ?? 'football') as (typeof SPORT_OPTIONS)[number]['code'])}
                  watchlist={watchlist}
                />
              )
            })}
          </CardGrid>
        )}
      </Section>

      {/* Assistant */}
      <InfinityPanel tone="var(--infinity-signal)">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <InfinityLabel tone="var(--infinity-signal)">TitanIQ Assistant</InfinityLabel>
            <p className="mt-1 font-infinity-body text-[13px] text-infinity-text-secondary">
              Ask about a prediction, compare teams, or explore what's connected in the Knowledge Graph.
            </p>
          </div>
          <Link
            to="/app/insights"
            className="inline-flex h-9 shrink-0 items-center gap-2 rounded-infinity-sm bg-infinity-signal px-4 font-infinity-body text-[13px] font-medium text-infinity-ground-0 transition-colors hover:bg-infinity-signal-hover"
          >
            <Sparkles className="size-3.5" aria-hidden="true" /> Open Assistant
          </Link>
        </div>
      </InfinityPanel>
    </div>
  )
}

function sortByKickoff<T extends { fixture: FixtureSummaryDto }>(items: T[]): T[] {
  return [...items].sort((a, b) => new Date(a.fixture.scheduled_at).getTime() - new Date(b.fixture.scheduled_at).getTime())
}

function FixtureCard({
  fixture,
  sportSlug,
  aiAvailable,
  watchlist,
}: {
  fixture: FixtureSummaryDto
  sportSlug: string
  aiAvailable: boolean
  watchlist: ReturnType<typeof useWatchlist>
}) {
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const domain = sportSlug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  return (
    <InfinityMatchCard
      sport={domain}
      competition={fixture.competition_name}
      competitionLogoUrl={fixture.competition_logo_url}
      status={fixtureCardStatus(fixture.status)}
      kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
      venue={fixture.venue_name}
      homeTeam={fixture.home_team?.name ?? 'TBD'}
      awayTeam={fixture.away_team?.name ?? 'TBD'}
      homeScore={homeScore}
      awayScore={awayScore}
      homeLogoUrl={fixture.home_team?.logo_url}
      awayLogoUrl={fixture.away_team?.logo_url}
      aiAvailable={aiAvailable}
      following={watchlist.isFollowing('fixture', fixture.id)}
      onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
      href={`/app/${sportSlug}/matches/${fixture.id}`}
    />
  )
}

function rankCompetitionsByActivity(fixtures: FixtureSummaryDto[]): Array<{ name: string; count: number }> {
  const counts = new Map<string, number>()
  for (const f of fixtures) counts.set(f.competition_name, (counts.get(f.competition_name) ?? 0) + 1)
  return [...counts.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count)
}

function HeroStat({
  icon: Icon,
  label,
  value,
  live,
}: {
  icon: typeof Radio
  label: string
  value: number | undefined
  live?: boolean
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="font-infinity-body text-[11px] text-infinity-text-muted">{label}</p>
        <Icon className={live ? 'size-3.5 text-infinity-live' : 'size-3.5 text-infinity-text-muted'} aria-hidden="true" />
      </div>
      <div className="mt-1 font-infinity-telemetry text-xl font-semibold text-infinity-text-primary">
        {value === undefined ? <InfinitySkeleton className="h-6 w-8" /> : value}
      </div>
    </div>
  )
}

function Section({
  icon: Icon,
  title,
  viewAllHref,
  tone = 'var(--infinity-text-muted)',
  children,
}: {
  icon: typeof Radio
  title: string
  viewAllHref: string
  tone?: string
  children: ReactNode
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Icon className="size-4" style={{ color: tone }} aria-hidden="true" />
          <InfinityLabel tone={tone}>{title}</InfinityLabel>
        </div>
        <Link to={viewAllHref} className="font-infinity-body text-[12px] text-infinity-signal hover:text-infinity-signal-hover">
          View all →
        </Link>
      </div>
      {children}
    </section>
  )
}

function CardGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}

function SkeletonRow({ count, tall, short }: { count: number; tall?: boolean; short?: boolean }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <InfinitySkeleton key={i} className={tall ? 'h-28' : short ? 'h-16' : 'h-24'} />
      ))}
    </div>
  )
}
