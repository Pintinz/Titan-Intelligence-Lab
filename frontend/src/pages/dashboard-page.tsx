import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { BarChart3, Gauge, Network, Newspaper, Star, Trophy, TrendingUp } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Skeleton } from '@/components/ui/skeleton'
import { PredictionCard } from '@/components/domain/prediction-card'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { Timeline, type TimelineEntry } from '@/components/domain/timeline'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { intelligenceApi } from '@/lib/api/intelligence'
import { subscribeToTable, type RealtimeTableKey } from '@/lib/realtime'
import { useAuthStore } from '@/stores/auth-store'
import { staggerContainer, staggerItem, transitionFast } from '@/lib/motion'
import { cn } from '@/lib/cn'

const ACTIVITY_TABLES: Array<{ key: RealtimeTableKey; label: string; tone: TimelineEntry['tone'] }> = [
  { key: 'predictions', label: 'Prediction updated', tone: 'info' },
  { key: 'providerIncidents', label: 'Provider incident', tone: 'danger' },
]

const QUICK_ACTIONS = [
  { to: '/app/predictions', label: 'Prediction Center', icon: TrendingUp },
  { to: '/app/matches', label: 'Match Center', icon: Trophy },
  { to: '/app/graph', label: 'Knowledge Graph', icon: Network },
  { to: '/app/analytics', label: 'Analytics', icon: BarChart3 },
]

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

export function DashboardPage() {
  const profile = useAuthStore((s) => s.profile)
  const [activity, setActivity] = useState<TimelineEntry[]>([])

  const marketsQuery = useQuery({ queryKey: ['markets', 'list'], queryFn: () => marketsApi.list({ status: 'production' }) })
  const firstMarket = marketsQuery.data?.[0]

  const predictionsQuery = useQuery({
    queryKey: ['predictions', 'byMarket', firstMarket?.id, 'dashboard'],
    queryFn: () => predictionsApi.list(firstMarket!.id, { limit: 3 }),
    enabled: Boolean(firstMarket),
  })

  const newsQuery = useQuery({ queryKey: ['intelligence', 'newsTimeline', 'dashboard'], queryFn: () => intelligenceApi.newsTimeline({ limit: 5 }) })

  const monitoringQuery = useQuery({
    queryKey: ['predictions', 'monitoringSummary', 'dashboard'],
    queryFn: () => predictionsApi.monitoringSummary(20),
  })

  useEffect(() => {
    const unsubscribes = ACTIVITY_TABLES.map(({ key, label, tone }) =>
      subscribeToTable(key, (payload) => {
        setActivity((prev) =>
          [
            { id: `${key}-${prev.length}-${payload.eventType}`, timestamp: new Date().toISOString(), title: label, description: payload.eventType, tone },
            ...prev,
          ].slice(0, 5),
        )
      }),
    )
    return () => unsubscribes.forEach((unsub) => unsub())
  }, [])

  const emailLocalPart = useMemo(() => profile?.email?.split('@')[0] ?? '', [profile?.email])

  return (
    <div data-dashboard-accent="executive" className="flex flex-col gap-6 p-6">
      <div
        className="relative overflow-hidden rounded-xl border border-border-glass bg-bg-glass p-6 backdrop-blur-[var(--blur-glass-md)]"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Executive Intelligence</p>
            <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">
              {greeting()}{emailLocalPart ? `, ${emailLocalPart}` : ''} <span aria-hidden="true">👋</span>
            </h1>
            <p className="mt-1 text-sm text-text-secondary">Today&apos;s intelligence, at a glance.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {QUICK_ACTIONS.map(({ to, label, icon: Icon }) => (
              <Button key={to} asChild variant="secondary" size="sm" className="bg-bg-glass-strong">
                <Link to={to} className="flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                  {label}
                </Link>
              </Button>
            ))}
          </div>
        </div>
      </div>

      <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid gap-6 lg:grid-cols-3">
        <motion.div variants={staggerItem} className="flex flex-col gap-3 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="flex items-center gap-2 font-display text-base font-semibold text-text-primary">
              <TrendingUp className="h-4 w-4 text-accent-primary" aria-hidden="true" />
              Today&apos;s predictions
            </h2>
            <Button asChild variant="ghost" size="sm">
              <Link to="/app/predictions">View all</Link>
            </Button>
          </div>

          {predictionsQuery.isLoading && <Skeleton className="h-40" />}
          {predictionsQuery.data && predictionsQuery.data.length === 0 && (
            <EmptyState title="No predictions yet" description="Predictions for today's production markets will appear here." />
          )}
          {predictionsQuery.data && predictionsQuery.data.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              {predictionsQuery.data.map((prediction) => (
                <HoverLift key={prediction.id}>
                  <PredictionCard prediction={prediction} />
                </HoverLift>
              ))}
            </div>
          )}
        </motion.div>

        <motion.div variants={staggerItem} className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 font-display text-base font-semibold text-text-primary">
            <Star className="h-4 w-4 text-accent-secondary" aria-hidden="true" />
            Favorite teams
          </h2>
          <EmptyState
            title="Coming soon"
            description="TitanIQ doesn't have a favorites/watchlist feature yet — this is a placeholder for when it does, not a fake list."
          />
        </motion.div>
      </motion.div>

      <motion.div variants={staggerContainer} initial="initial" animate="animate" className="grid gap-6 lg:grid-cols-3">
        <motion.div variants={staggerItem}>
          <HoverLift>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Newspaper className="h-4 w-4 text-accent-primary" aria-hidden="true" />
                  Latest news
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {newsQuery.isLoading && <Skeleton className="h-24" />}
                {newsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No recent news events.</p>}
                {newsQuery.data?.map((event) => (
                  <div key={event.id} className="border-b border-border-subtle py-2 text-sm last:border-0">
                    <p className="text-text-primary">{event.headline}</p>
                    <p className="font-mono text-xs text-text-muted">{new Date(event.occurred_at).toLocaleString()}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          </HoverLift>
        </motion.div>

        <motion.div variants={staggerItem}>
          <HoverLift>
            <Card className="h-full">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-accent-primary" aria-hidden="true" />
                  Model health
                </CardTitle>
              </CardHeader>
              <CardContent>
                {monitoringQuery.isLoading && <Skeleton className="h-24" />}
                {monitoringQuery.data && <KeyValueGrid data={monitoringQuery.data} />}
              </CardContent>
            </Card>
          </HoverLift>
        </motion.div>

        <motion.div variants={staggerItem}>
          <HoverLift>
            <Card className="h-full">
              <CardHeader>
                <CardTitle>Recent activity</CardTitle>
              </CardHeader>
              <CardContent>
                {activity.length === 0 ? (
                  <p className="text-sm text-text-muted">Live events will appear here as they happen.</p>
                ) : (
                  <Timeline entries={activity} />
                )}
              </CardContent>
            </Card>
          </HoverLift>
        </motion.div>
      </motion.div>
    </div>
  )
}

function HoverLift({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div whileHover={{ y: -3 }} transition={transitionFast} className={cn('h-full', className)}>
      {children}
    </motion.div>
  )
}
