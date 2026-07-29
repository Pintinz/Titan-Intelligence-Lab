import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Trophy } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { SportTabs } from '@/components/domain/sport-tabs'
import { MatchCard } from '@/components/domain/match-card'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { staggerContainer, staggerItem } from '@/lib/motion'

const STATUS_FILTERS = ['all', 'live', 'scheduled', 'completed'] as const

export default function MatchCenterPage() {
  const [sport, setSport] = useState<SportCode>('football')
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>('all')

  const fixturesQuery = useQuery({
    queryKey: ['sports', 'fixtures', sport],
    queryFn: () => sportsApi.listFixtures(sport, { limit: 50 }),
  })

  useRealtimeInvalidate('matches', [['sports', 'fixtures', sport]])

  const fixtures = fixturesQuery.data ?? []
  const featured = useMemo(
    () => fixtures.find((f) => f.status === 'live') ?? fixtures.find((f) => f.status === 'scheduled'),
    [fixtures],
  )
  const filtered = useMemo(
    () => (statusFilter === 'all' ? fixtures : fixtures.filter((f) => f.status === statusFilter)),
    [fixtures, statusFilter],
  )

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Match Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Match Center</h1>
      </div>

      <SportTabs value={sport} onChange={setSport} />

      {featured && (
        <Link to={`/app/matches/${featured.id}`}>
          <div
            className="overflow-hidden rounded-lg border border-border-default p-6 transition-colors hover:border-border-strong"
            style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
          >
            <div className="flex items-center justify-between text-xs text-text-muted">
              <span>{featured.competition_name}</span>
              <Badge variant={featured.status === 'live' ? 'danger' : 'neutral'} className={featured.status === 'live' ? 'animate-pulse' : undefined}>
                {featured.status === 'live' ? 'Live now' : 'Next up'}
              </Badge>
            </div>
            <div className="mt-4 flex items-center justify-center gap-6">
              <div className="flex flex-col items-center gap-2">
                <TeamMonogramBadge id={featured.home_team.id} name={featured.home_team.name} size={48} />
                <span className="text-sm font-medium text-text-primary">{featured.home_team.short_name}</span>
              </div>
              <span className="font-mono text-xs text-text-muted">vs</span>
              <div className="flex flex-col items-center gap-2">
                <TeamMonogramBadge id={featured.away_team.id} name={featured.away_team.name} size={48} />
                <span className="text-sm font-medium text-text-primary">{featured.away_team.short_name}</span>
              </div>
            </div>
            <p className="mt-4 text-center text-xs text-text-muted">{new Date(featured.scheduled_at).toLocaleString()}</p>
          </div>
        </Link>
      )}

      <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v as (typeof STATUS_FILTERS)[number])}>
        <SelectTrigger className="w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {STATUS_FILTERS.map((status) => (
            <SelectItem key={status} value={status}>
              {status === 'all' ? 'All statuses' : status}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {fixturesQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {fixturesQuery.isError && <ErrorState description="Could not load fixtures." onRetry={() => fixturesQuery.refetch()} />}

      {fixturesQuery.data && filtered.length === 0 && (
        <EmptyState icon={<Trophy className="h-6 w-6" />} title="No fixtures found" description="No fixtures match this filter yet." />
      )}

      {fixturesQuery.data && filtered.length > 0 && (
        <motion.div
          variants={staggerContainer}
          initial="initial"
          animate="animate"
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        >
          {filtered.map((fixture) => (
            <motion.div key={fixture.id} variants={staggerItem}>
              <MatchCard fixture={fixture} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}
