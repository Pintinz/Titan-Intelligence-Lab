import { useQuery } from '@tanstack/react-query'
import { MessageSquare } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { intelligenceApi } from '@/lib/api/intelligence'

export default function CommunityCenterPage() {
  const topicsQuery = useQuery({ queryKey: ['intelligence', 'communityTopics'], queryFn: () => intelligenceApi.communityTopics() })

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Community Center' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Community Center</h1>
        <p className="mt-1 text-sm text-text-secondary">Trending topics across tracked community platforms.</p>
      </div>

      {topicsQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {topicsQuery.isError && <ErrorState description="Could not load community topics." onRetry={() => topicsQuery.refetch()} />}

      {topicsQuery.data && topicsQuery.data.length === 0 && (
        <EmptyState icon={<MessageSquare className="h-6 w-6" />} title="No community topics found" />
      )}

      {topicsQuery.data && topicsQuery.data.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {topicsQuery.data.map((topic) => (
            <Card key={topic.id}>
              <CardHeader className="flex-row items-center justify-between">
                <CardTitle className="text-sm">{topic.title}</CardTitle>
                <Badge variant="neutral">{topic.platform}</Badge>
              </CardHeader>
              <CardContent className="flex items-center justify-between text-xs text-text-muted">
                <span>Volume: {topic.volume}</span>
                {topic.sentiment_score !== null && (
                  <span className={topic.sentiment_score >= 0 ? 'text-success' : 'text-danger'}>
                    sentiment {topic.sentiment_score.toFixed(2)}
                  </span>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
