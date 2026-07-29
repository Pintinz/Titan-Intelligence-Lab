import { useQuery } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { TeamCard } from '@/components/domain/team-card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

export default function TeamListPage() {
  const sport = useSportParam()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'teams', sport?.code],
    queryFn: () => sportsApi.listTeams(sport!.code),
    enabled: !!sport,
  })

  if (!sport) return null

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Team Intelligence
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{sport.label} teams</h2>
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <EmptyState icon={Users} title="No teams found" description={`No ${sport.label} teams are under coverage.`} />
      )}

      {data && data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {data.map((team) => (
            <TeamCard key={team.id} team={team} sportSlug={sport.slug} />
          ))}
        </div>
      )}
    </div>
  )
}
