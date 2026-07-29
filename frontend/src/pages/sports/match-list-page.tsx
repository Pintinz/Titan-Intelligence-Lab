import { useQuery } from '@tanstack/react-query'
import { CalendarX } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { FixtureCard } from '@/components/domain/fixture-card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function MatchListPage() {
  const sport = useSportParam()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'fixtures', sport?.code, 'list'],
    queryFn: () => sportsApi.listFixtures(sport!.code, { limit: 50 }),
    enabled: !!sport,
  })

  if (!sport) return null

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Match Intelligence
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{sport.label} matches</h2>
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <EmptyState icon={CalendarX} title="No matches found" description={`No ${sport.label} fixtures are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((fixture) => (
            <FixtureCard key={fixture.id} fixture={fixture} sportSlug={sport.slug} />
          ))}
        </div>
      )}
    </div>
  )
}
