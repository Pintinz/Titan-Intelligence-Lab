import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { SportTabs } from '@/components/domain/sport-tabs'
import { TeamCard } from '@/components/domain/team-card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { sportsApi, type SportCode } from '@/lib/api/sports'

export default function TeamCenterPage() {
  const [sport, setSport] = useState<SportCode>('football')

  const teamsQuery = useQuery({ queryKey: ['sports', 'teams', sport], queryFn: () => sportsApi.listTeams(sport) })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Team Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Team Center</h1>
      </div>

      <SportTabs value={sport} onChange={setSport} />

      {teamsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {teamsQuery.isError && <ErrorState description="Could not load teams." onRetry={() => teamsQuery.refetch()} />}

      {teamsQuery.data && teamsQuery.data.length === 0 && <EmptyState icon={<Users className="h-6 w-6" />} title="No teams found" />}

      {teamsQuery.data && teamsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {teamsQuery.data.map((team) => (
            <TeamCard key={team.id} team={team} />
          ))}
        </div>
      )}
    </div>
  )
}
