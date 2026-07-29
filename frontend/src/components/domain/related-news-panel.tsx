import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { intelligenceApi } from '@/lib/api/intelligence'

/** Cross-links News Intelligence into match/team/player detail pages via newsForEntity — the
 * single highest-value "seamless platform" gap the Milestone 10B audit found (news tied to the
 * entity being viewed had no frontend caller anywhere before this). */
export function RelatedNewsPanel({ entityRef }: { entityRef: string }) {
  const newsQuery = useQuery({
    queryKey: ['intelligence', 'newsForEntity', entityRef],
    queryFn: () => intelligenceApi.newsForEntity(entityRef, 10),
    retry: false,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Related news</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {newsQuery.isLoading && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10" />
            ))}
          </div>
        )}
        {newsQuery.data?.map((event) => (
          <div key={event.id} className="flex items-start justify-between gap-3 border-b border-border-subtle py-2 last:border-0">
            <div>
              <p className="text-sm text-text-primary">{event.headline}</p>
              <p className="font-mono text-xs text-text-muted">{new Date(event.occurred_at).toLocaleDateString()}</p>
            </div>
            <Badge variant="neutral">{event.category}</Badge>
          </div>
        ))}
        {newsQuery.data?.length === 0 && <p className="text-sm text-text-muted">No recent news mentions this entity.</p>}
      </CardContent>
    </Card>
  )
}
