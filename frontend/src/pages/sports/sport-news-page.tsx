import { useQuery } from '@tanstack/react-query'
import { Newspaper } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { useSportParam } from '@/lib/hooks/use-sport'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * `intelligenceApi.searchNews` has no sport-level filter (backend gap — the endpoint takes a
 * free-text `query`, not an entity/sport scope), so this uses the sport label as a best-effort
 * text search. A precise scope would need either client-side filtering against every team/
 * competition name for the sport, or a small additive backend filter — not worth either yet for
 * a text search that already works reasonably well.
 */
export default function SportNewsPage() {
  const sport = useSportParam()
  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['intelligence', 'news', sport?.label],
    queryFn: () => intelligenceApi.searchNews({ query: sport!.label, limit: 20 }),
    enabled: !!sport,
  })

  if (!sport) return null

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          News Intelligence
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{sport.label} news</h2>
      </div>

      {isPending && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <EmptyState icon={Newspaper} title="No news yet" description={`No ${sport.label} coverage matched right now.`} />
      )}

      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((article) => (
            <Card key={article.id} className="p-4">
              <p className="font-mono text-[11px] text-text-muted">
                {new Date(article.published_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
              </p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{article.title}</p>
              {article.entities.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {article.entities.map((entity) => (
                    <span key={entity} className="rounded-full border border-border-default px-2 py-0.5 text-[10px] text-text-muted">
                      {entity}
                    </span>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
