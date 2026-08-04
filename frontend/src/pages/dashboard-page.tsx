import { useQueries, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  Radio,
  CalendarDays,
  Gauge,
  Network,
  Newspaper,
  Trophy,
  Sparkles,
  GraduationCap,
  Share2,
} from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { intelligenceApi } from '@/lib/api/intelligence'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { FixtureCard } from '@/components/domain/fixture-card'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { useAuthStore } from '@/stores/auth-store'

function isLive(status: string) {
  const s = status.toLowerCase()
  return s === 'live' || s === 'in_play'
}

function isToday(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  return d.toDateString() === now.toDateString()
}

const QUICK_LINKS = [
  { label: 'News Intelligence', href: '/app/news', icon: Newspaper },
  { label: 'Learning Intelligence', href: '/app/learning', icon: GraduationCap },
  { label: 'TitanIQ Insights', href: '/app/insights', icon: Sparkles },
  { label: 'Knowledge Graph', href: '/app/graph', icon: Share2 },
]

export default function DashboardPage() {
  const profile = useAuthStore((s) => s.profile)

  const fixtureQueries = useQueries({
    queries: SPORT_SLUGS.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'dashboard'],
      queryFn: () => sportsApi.listFixtures(sport.code, { limit: 8 }),
    })),
  })

  // Live match state (score/status) across every sport pushes straight into the fixture tiles
  // below — no polling interval, no manual refresh.
  useRealtimeInvalidate(
    'matches',
    SPORT_SLUGS.map((sport) => ['sports', sport.code, 'fixtures', 'dashboard']),
  )

  const monitoringQuery = useQuery({
    queryKey: ['predictions', 'monitoring', 'summary'],
    queryFn: () => predictionsApi.monitoringSummary(),
  })
  const graphStatsQuery = useQuery({
    queryKey: ['graph', 'statistics'],
    queryFn: () => graphApi.statistics(),
  })
  const intelligenceAnalyticsQuery = useQuery({
    queryKey: ['intelligence', 'analytics'],
    queryFn: () => intelligenceApi.analytics(),
  })

  const allFixtures = fixtureQueries.flatMap((q) => q.data ?? [])
  const liveCount = allFixtures.filter((f) => isLive(f.status)).length
  const todayCount = allFixtures.filter((f) => isToday(f.scheduled_at)).length
  const anyFixturesLoading = fixtureQueries.some((q) => q.isPending)
  const firstName = profile?.email?.split('@')[0]

  return (
    <div className="mx-auto max-w-5xl space-y-10 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Dashboard
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">
          {firstName ? `Welcome back, ${firstName}` : 'Welcome back'}
        </h1>
        <p className="mt-1 text-sm text-text-secondary">
          Everything TitanIQ is tracking right now, across every Sport Intelligence Center.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-muted">Live now</p>
            <Radio className={liveCount > 0 ? 'size-4 text-live' : 'size-4 text-text-muted'} aria-hidden="true" />
          </div>
          <div className="mt-2 font-telemetry text-2xl font-medium text-text-primary">
            {anyFixturesLoading ? <Skeleton className="h-7 w-8" /> : liveCount}
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-muted">Matches today</p>
            <CalendarDays className="size-4 text-accent-primary" aria-hidden="true" />
          </div>
          <div className="mt-2 font-telemetry text-2xl font-medium text-text-primary">
            {anyFixturesLoading ? <Skeleton className="h-7 w-8" /> : todayCount}
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-muted">Predictions tracked</p>
            <Gauge className="size-4 text-accent-primary" aria-hidden="true" />
          </div>
          <div className="mt-2 font-telemetry text-2xl font-medium text-text-primary">
            {monitoringQuery.isPending ? (
              <Skeleton className="h-7 w-8" />
            ) : (
              (monitoringQuery.data?.sample_size as number | undefined) ?? '—'
            )}
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-text-muted">Knowledge Graph nodes</p>
            <Network className="size-4 text-accent-primary" aria-hidden="true" />
          </div>
          <div className="mt-2 font-telemetry text-2xl font-medium text-text-primary">
            {graphStatsQuery.isPending ? (
              <Skeleton className="h-7 w-8" />
            ) : (
              (graphStatsQuery.data?.node_count as number | undefined) ?? '—'
            )}
          </div>
        </Card>
      </div>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <Trophy className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Today across every sport</p>
        </div>
        <div className="space-y-6">
          {SPORT_SLUGS.map((sport, i) => {
            const query = fixtureQueries[i]
            return (
              <div key={sport.code}>
                <div className="mb-2 flex items-center justify-between">
                  <Link
                    to={`/app/${sport.slug}`}
                    className="text-xs font-medium uppercase tracking-wide text-text-muted hover:text-accent-primary"
                  >
                    {sport.label}
                  </Link>
                  <Link to={`/app/${sport.slug}/matches`} className="text-xs text-accent-primary hover:text-accent-primary-hover">
                    View all →
                  </Link>
                </div>
                {query.isPending && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    {Array.from({ length: 3 }).map((_, si) => <Skeleton key={si} className="h-24" />)}
                  </div>
                )}
                {query.isError && <ErrorState error={query.error} onRetry={() => void query.refetch()} />}
                {query.data && query.data.length === 0 && (
                  <EmptyState
                    variant="minimal"
                    title={`No ${sport.label.toLowerCase()} fixtures yet`}
                    description="Nothing has synced from a data provider for this sport yet."
                  />
                )}
                {query.data && query.data.length > 0 && (
                  <div className="grid gap-3 sm:grid-cols-3">
                    {query.data.slice(0, 3).map((fixture) => (
                      <FixtureCard key={fixture.id} fixture={fixture} sportSlug={sport.slug} />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <Gauge className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Prediction intelligence</p>
        </div>
        <Card className="p-5">
          {monitoringQuery.isPending && <Skeleton className="h-20" />}
          {monitoringQuery.isError && (
            <ErrorState error={monitoringQuery.error} onRetry={() => void monitoringQuery.refetch()} />
          )}
          {monitoringQuery.data && <KeyValueGrid data={monitoringQuery.data} />}
        </Card>
      </section>

      <div className="grid gap-6 sm:grid-cols-2">
        <section>
          <div className="mb-4 flex items-center gap-2">
            <Network className="size-4 text-accent-primary" aria-hidden="true" />
            <p className="text-sm font-medium text-text-primary">Knowledge Graph</p>
          </div>
          <Card className="p-5">
            {graphStatsQuery.isPending && <Skeleton className="h-20" />}
            {graphStatsQuery.isError && (
              <ErrorState error={graphStatsQuery.error} onRetry={() => void graphStatsQuery.refetch()} />
            )}
            {graphStatsQuery.data && <KeyValueGrid data={graphStatsQuery.data} />}
          </Card>
        </section>

        <section>
          <div className="mb-4 flex items-center gap-2">
            <Newspaper className="size-4 text-accent-primary" aria-hidden="true" />
            <p className="text-sm font-medium text-text-primary">News & community intelligence</p>
          </div>
          <Card className="p-5">
            {intelligenceAnalyticsQuery.isPending && <Skeleton className="h-20" />}
            {intelligenceAnalyticsQuery.isError && (
              <ErrorState error={intelligenceAnalyticsQuery.error} onRetry={() => void intelligenceAnalyticsQuery.refetch()} />
            )}
            {intelligenceAnalyticsQuery.data && <KeyValueGrid data={intelligenceAnalyticsQuery.data} />}
          </Card>
        </section>
      </div>

      <section>
        <div className="flex flex-wrap gap-2">
          {QUICK_LINKS.map((link) => (
            <Link
              key={link.href}
              to={link.href}
              className="inline-flex items-center gap-1.5 rounded-full border border-border-default px-3 py-1.5 text-xs text-text-secondary hover:border-accent-primary hover:text-accent-primary"
            >
              <link.icon className="size-3.5" aria-hidden="true" />
              {link.label}
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
