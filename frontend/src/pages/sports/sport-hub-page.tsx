import { useQuery } from '@tanstack/react-query'
import { Radio } from 'lucide-react'
import { cn } from '@/lib/cn'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores, isLiveStatus } from '@/lib/sports-status'
import { InfinityLabel, InfinityPanel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { ErrorState } from '@/components/ui/error-state'
import type { DomainKey } from '@/components/infinity/primitives/badge'
import type { FixtureSummaryDto } from '@/lib/api/types'

export default function SportHubPage() {
  const sport = useSportParam()
  const watchlist = useWatchlist()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'fixtures', sport?.code, 'hub'],
    queryFn: () => sportsApi.listFixtures(sport!.code, { limit: 12 }),
    enabled: !!sport,
    refetchInterval: 30_000,
  })
  // Same "does this sport have a live, trained market" signal the Matches tab and Mission
  // Control already use for the AI badge/CTA on match cards — reused here, not recomputed.
  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
    staleTime: 5 * 60 * 1000,
  })
  const syncStatusQuery = useQuery({
    queryKey: ['sports', 'sync-status', 'hub'],
    queryFn: () => sportsApi.syncStatus(),
    refetchInterval: 60_000,
  })
  const aiAvailable = (marketsQuery.data?.length ?? 0) > 0

  if (!sport) return null

  const live = (data ?? []).filter((f) => isLiveStatus(f.status))
  const rest = (data ?? []).filter((f) => !isLiveStatus(f.status))
  const trackedCompetitions = new Set((data ?? []).map((f) => f.competition_name)).size

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Live Intelligence</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          What's happening in {sport.label} right now
        </h2>
      </div>

      <IntelligencePulse
        loading={isPending}
        inView={data?.length ?? 0}
        liveCount={live.length}
        competitions={trackedCompetitions}
        marketsLoading={marketsQuery.isPending}
        aiAvailable={aiAvailable}
        lastSyncedAt={syncStatusQuery.data?.last_synced_at}
      />

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState
          icon={Radio}
          title="No fixtures under coverage"
          description={`TitanIQ has no ${sport.label} fixtures scheduled right now.`}
        />
      )}

      {live.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-1.5">
            <span className="size-1.5 animate-pulse rounded-full bg-infinity-live" aria-hidden="true" />
            <InfinityLabel tone="var(--infinity-live)">Live now</InfinityLabel>
          </div>
          <FixtureGrid fixtures={live} sport={sport} watchlist={watchlist} aiAvailable={aiAvailable} />
        </div>
      )}

      {rest.length > 0 && (
        <div className="space-y-3">
          {live.length > 0 && <InfinityLabel>Coming up</InfinityLabel>}
          <FixtureGrid fixtures={rest} sport={sport} watchlist={watchlist} aiAvailable={aiAvailable} />
        </div>
      )}
    </div>
  )
}

function FixtureGrid({
  fixtures,
  sport,
  watchlist,
  aiAvailable,
}: {
  fixtures: FixtureSummaryDto[]
  sport: NonNullable<ReturnType<typeof useSportParam>>
  watchlist: ReturnType<typeof useWatchlist>
  aiAvailable: boolean
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {fixtures.map((fixture) => {
        const { homeScore, awayScore } = fixtureScores(fixture.final_state)
        const status = fixtureCardStatus(fixture.status)
        return (
          <InfinityMatchCard
            key={fixture.id}
            sport={sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>}
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
            aiAvailable={status !== 'completed' && aiAvailable}
            following={watchlist.isFollowing('fixture', fixture.id)}
            onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
            href={status === 'completed' ? `/app/${sport.slug}/matches/${fixture.id}/review` : `/app/${sport.slug}/matches/${fixture.id}`}
          />
        )
      })}
    </div>
  )
}

/** A compact telemetry strip so "Live Intelligence" is a real reading, not just a page title —
 * every value here is derived from data already fetched on this page (or the same production-
 * market/sync-status signals every other discovery surface uses), never a fabricated metric. */
function IntelligencePulse({
  loading,
  inView,
  liveCount,
  competitions,
  marketsLoading,
  aiAvailable,
  lastSyncedAt,
}: {
  loading: boolean
  inView: number
  liveCount: number
  competitions: number
  marketsLoading: boolean
  aiAvailable: boolean
  lastSyncedAt: string | null | undefined
}) {
  if (loading) return <InfinitySkeleton className="h-16" />

  const items: Array<{ label: string; value: string; tone?: 'live' | 'ready' }> = [
    { label: 'In view', value: String(inView) },
    { label: 'Live now', value: liveCount > 0 ? String(liveCount) : 'None', tone: liveCount > 0 ? 'live' : undefined },
    { label: 'Competitions', value: String(competitions) },
    { label: 'AI markets', value: marketsLoading ? '…' : aiAvailable ? 'Ready' : 'Building', tone: aiAvailable ? 'ready' : undefined },
    { label: 'Last synced', value: formatLastSync(lastSyncedAt) },
  ]

  return (
    <InfinityPanel tone="var(--infinity-signal)" className="flex flex-wrap divide-x divide-infinity-border-hairline !p-0">
      {items.map((item) => (
        <div key={item.label} className="min-w-[6.5rem] flex-1 px-4 py-3 first:pl-4">
          <p className="font-infinity-mono text-[9px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted">{item.label}</p>
          <p
            className={cn(
              'mt-0.5 flex items-center gap-1.5 font-infinity-telemetry text-sm font-semibold tabular-nums',
              item.tone === 'live' ? 'text-infinity-live' : item.tone === 'ready' ? 'text-[var(--infinity-signal)]' : 'text-infinity-text-primary',
            )}
          >
            {item.tone === 'live' && <span className="size-1.5 shrink-0 animate-pulse rounded-full bg-infinity-live" aria-hidden="true" />}
            {item.value}
          </p>
        </div>
      ))}
    </InfinityPanel>
  )
}

function formatLastSync(lastSyncedAt: string | null | undefined): string {
  if (!lastSyncedAt) return 'Pending'
  return new Date(lastSyncedAt).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}
