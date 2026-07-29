import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Trophy } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { SportTabs } from '@/components/domain/sport-tabs'
import { CompetitionCard } from '@/components/domain/competition-card'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { sportsApi, type SportCode } from '@/lib/api/sports'

export default function CompetitionCenterPage() {
  const [sport, setSport] = useState<SportCode>('football')

  const competitionsQuery = useQuery({
    queryKey: ['sports', 'competitions', sport],
    queryFn: () => sportsApi.listCompetitions(sport),
  })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Competition Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Competition Center</h1>
      </div>

      <SportTabs value={sport} onChange={setSport} />

      {competitionsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {competitionsQuery.isError && (
        <ErrorState description="Could not load competitions." onRetry={() => competitionsQuery.refetch()} />
      )}

      {competitionsQuery.data && competitionsQuery.data.length === 0 && (
        <EmptyState icon={<Trophy className="h-6 w-6" />} title="No competitions found" />
      )}

      {competitionsQuery.data && competitionsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {competitionsQuery.data.map((competition) => (
            <CompetitionCard key={competition.id} competition={competition} />
          ))}
        </div>
      )}
    </div>
  )
}
