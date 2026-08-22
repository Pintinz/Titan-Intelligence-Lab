import { useQueries, useQuery } from '@tanstack/react-query'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { intelligenceApi } from '@/lib/api/intelligence'
import { useAvailableSports } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { isLiveStatus } from '@/lib/sports-status'
import { todayRange } from '@/lib/sports-date-ranges'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { getDisplayNameFromEmail, getTimeAwareGreeting } from '@/lib/user-display-name'
import { MissionHero, type MissionHeroStatus, type SystemStatusTone } from '@/components/command-deck/mission-control/mission-hero'
import { AiOperationsOverview, type OperationsMetric } from '@/components/command-deck/mission-control/ai-operations-overview'
import { LiveIntelligence, type FixtureCardItem } from '@/components/command-deck/mission-control/live-intelligence'
import { AiReadyFixtures } from '@/components/command-deck/mission-control/ai-ready-fixtures'
import { TopAiIntelligence } from '@/components/command-deck/mission-control/top-ai-intelligence'
import { IntelligenceFeed } from '@/components/command-deck/mission-control/intelligence-feed'
import { CompetitionsUnderWatch } from '@/components/command-deck/mission-control/competitions-under-watch'
import { RecentlyCompletedCrossSport } from '@/components/command-deck/mission-control/recently-completed-cross-sport'
import { FollowingSection } from '@/components/command-deck/mission-control/following-section'
import { WorkspaceTeaser } from '@/components/command-deck/mission-control/workspace-teaser'
import { MissionAmbientBackground } from '@/components/command-deck/mission-control/mission-ambient-background'

/**
 * Mission Control — Command Deck. Every section here caps at 6 cards and reads from a real,
 * already-existing backend endpoint; nothing is fabricated. Several sections reuse an existing
 * component outright (`AiPickCard`+dedup for Top AI Intelligence, `RecentlyCompletedIntelligence`
 * generalized across sports) instead of a second implementation. Data-fetching for Live/AI Ready/
 * Overview all lives here once (this page's own cross-sport `useQueries` pattern) so no section
 * below re-fetches what this page already has; sections that are self-contained (Intelligence
 * Feed, Competitions Under Watch, Following, Top AI Intelligence) use the exact same React Query
 * keys a sibling section already reads where the same data applies, so TanStack Query dedupes the
 * network call automatically rather than this page prop-drilling every value.
 */
export default function HomePage() {
  const profile = useAuthStore((s) => s.profile)
  const watchlist = useWatchlist()
  const displayName = getDisplayNameFromEmail(profile?.email)
  const greeting = getTimeAwareGreeting()
  const isAdmin = !!profile && isAtLeast(profile.role, 'administrator')
  // Basketball/Baseball/Table Tennis are still under development — regular users only see
  // Football here, matching the same gate the backend enforces server-side.
  const sports = useAvailableSports()

  const liveQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'live'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'live', limit: 50 }),
      refetchInterval: 30_000,
    })),
  })
  const todayRangeValue = todayRange()
  const todayQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'today', todayRangeValue.from],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { date_from: todayRangeValue.from, date_to: todayRangeValue.to, limit: 50 }),
    })),
  })
  const marketQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['markets', sport.code, 'production'],
      queryFn: () => marketsApi.list({ sport_code: sport.code, status: 'production' }),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const aiAvailableBySport = new Set(sports.filter((_, i) => (marketQueries[i].data?.length ?? 0) > 0).map((s) => s.code))

  const anyLiveLoading = liveQueries.some((q) => q.isPending)
  const anyTodayLoading = todayQueries.some((q) => q.isPending)

  const liveWithSport: FixtureCardItem[] = sports.flatMap((sport, i) => (liveQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })))
  const todayWithSport: FixtureCardItem[] = sports.flatMap((sport, i) => (todayQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })))
  const todayNonLive = todayWithSport.filter((x) => !isLiveStatus(x.fixture.status))

  const todayIsEmpty = !anyTodayLoading && todayNonLive.length === 0
  const upcomingFallbackQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'home', 'upcoming-fallback'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'scheduled', limit: 6 }),
      enabled: todayIsEmpty,
    })),
  })
  const anyFallbackLoading = todayIsEmpty && upcomingFallbackQueries.some((q) => q.isPending)
  const upcomingFallbackWithSport: FixtureCardItem[] = sports.flatMap((sport, i) =>
    (upcomingFallbackQueries[i].data?.items ?? []).map((fixture) => ({ fixture, sport })),
  )
  const showUpcomingFallback = todayIsEmpty && !anyFallbackLoading && upcomingFallbackWithSport.length > 0
  const aiReadyItems = sortByKickoff(showUpcomingFallback ? upcomingFallbackWithSport : todayNonLive)
  const aiReadyLoading = showUpcomingFallback ? anyFallbackLoading : anyTodayLoading

  const monitoringQuery = useQuery({ queryKey: ['predictions', 'monitoring', 'summary', 'home'], queryFn: () => predictionsApi.monitoringSummary() })

  // Same query key Competitions Under Watch / Intelligence Feed use internally — TanStack Query
  // dedupes these into the exact same network request, so the Overview tiles below cost nothing
  // extra even though they need a total this page doesn't otherwise compute.
  const competitionCountQueries = useQueries({
    queries: sports.map((sport) => ({
      queryKey: ['sports', sport.code, 'competitions', 'mission-control'],
      queryFn: () => sportsApi.listCompetitions(sport.code),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const trackedCompetitions = competitionCountQueries.reduce((sum, q) => sum + (q.data?.length ?? 0), 0)

  const newsCountQuery = useQuery({ queryKey: ['intelligence', 'news', 'mission-control'], queryFn: () => intelligenceApi.searchNews({ limit: 8 }) })

  // Real "when did TitanIQ last pull data from a provider" reading, not derived from unrelated
  // content timestamps — polled so the Hero reflects a sync that happens while the page is open.
  const syncStatusQuery = useQuery({
    queryKey: ['sports', 'sync-status', 'mission-control'],
    queryFn: () => sportsApi.syncStatus(),
    refetchInterval: 60_000,
  })

  const predictionEngineStatus = deriveStatus(monitoringQuery.isPending, monitoringQuery.isError, 'Healthy', 'Checking', 'Degraded')
  const liveMonitoringStatus = deriveStatus(anyLiveLoading, liveQueries.every((q) => q.isError), 'Connected', 'Connecting', 'Offline')
  const lastSync = formatLastSync(syncStatusQuery.data?.last_synced_at)

  const heroStatus: MissionHeroStatus = {
    predictionEngine: predictionEngineStatus,
    liveMonitoring: liveMonitoringStatus,
    lastSync,
  }

  const overviewMetrics: OperationsMetric[] = [
    { label: 'Live matches', value: anyLiveLoading ? null : liveWithSport.length, description: 'Fixtures live across every covered sport right now.', status: liveWithSport.length > 0 ? { label: 'Live', tone: 'live' } : undefined },
    { label: "Today's fixtures", value: anyTodayLoading ? null : todayWithSport.length, description: "Everything scheduled today, across every covered sport." },
    { label: 'AI ready matches', value: aiReadyLoading || marketQueries.some((q) => q.isPending) ? null : aiReadyItems.filter((i) => aiAvailableBySport.has(i.sport.code)).length, description: 'Fixtures with a trained market ready to generate intelligence.', domain: 'predictions' },
    { label: 'Published intelligence', value: monitoringQuery.isPending ? null : ((monitoringQuery.data?.predictions_by_status as Record<string, number> | undefined)?.published ?? 0), description: 'Published predictions in the most recent sample.', domain: 'predictions' },
    { label: 'Tracked competitions', value: competitionCountQueries.some((q) => q.isPending) ? null : trackedCompetitions, description: 'Competitions under TitanIQ coverage across every sport.', domain: 'operations' },
    { label: 'Breaking stories', value: newsCountQuery.isPending ? null : newsCountQuery.data?.length ?? 0, description: 'Recently synced news articles.', domain: 'news' },
    { label: 'Following', value: watchlist.isPending ? null : (watchlist.data?.length ?? 0), description: 'Matches, teams and competitions you follow.' },
    { label: 'System health', value: undefined, description: 'Prediction Engine and live monitoring status.', status: { label: predictionEngineStatus.label, tone: predictionEngineStatus.tone }, domain: 'operations' },
  ]

  return (
    <div className="command-deck relative isolate space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <MissionAmbientBackground />

      <MissionHero greeting={greeting} name={displayName} isAdmin={isAdmin} status={heroStatus} />

      <AiOperationsOverview metrics={overviewMetrics} />

      <LiveIntelligence items={sortByKickoff(liveWithSport)} isLoading={anyLiveLoading} aiAvailableBySport={aiAvailableBySport} />

      <AiReadyFixtures items={aiReadyItems} isLoading={aiReadyLoading} isFallback={showUpcomingFallback} aiAvailableBySport={aiAvailableBySport} />

      <TopAiIntelligence />

      <IntelligenceFeed />

      <CompetitionsUnderWatch liveFixtures={liveWithSport} upcomingFixtures={todayWithSport} />

      <RecentlyCompletedCrossSport />

      <FollowingSection />

      <WorkspaceTeaser aiReadyFixtures={aiReadyItems} />
    </div>
  )
}

function sortByKickoff(items: FixtureCardItem[]): FixtureCardItem[] {
  return [...items].sort((a, b) => new Date(a.fixture.scheduled_at).getTime() - new Date(b.fixture.scheduled_at).getTime())
}

function deriveStatus(
  isLoading: boolean,
  isError: boolean,
  readyLabel: string,
  loadingLabel: string,
  errorLabel: string,
): { label: string; tone: SystemStatusTone } {
  if (isLoading) return { label: loadingLabel, tone: 'building' }
  if (isError) return { label: errorLabel, tone: 'idle' }
  return { label: readyLabel, tone: 'ready' }
}

function formatLastSync(lastSyncedAt: string | null | undefined): string | null {
  if (!lastSyncedAt) return null
  return new Date(lastSyncedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
