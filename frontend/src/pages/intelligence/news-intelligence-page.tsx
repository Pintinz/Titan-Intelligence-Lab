import { useQuery } from '@tanstack/react-query'
import { Newspaper, TrendingUp } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { Card } from '@/components/ui/card'
import { Tag } from '@/components/ui/tag'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * Articles, news events, and impact scores are three distinct backend entities
 * (NewsArticleDto / NewsEventDto / ImpactScoreDto) with no direct join field exposed to the
 * frontend — an article has no `news_event_id`, and impact scores are keyed to events, not
 * articles. Rather than fabricate a one-card-does-everything view the brief sketches, this page
 * is honest about the split: a real article feed (with a real "read original source" link) and a
 * separate Impact panel, best-effort matched to a headline from the events timeline when the ids
 * line up within the fetched window.
 */
export default function NewsIntelligencePage() {
  const articlesQuery = useQuery({
    queryKey: ['intelligence', 'news', 'search'],
    queryFn: () => intelligenceApi.searchNews({ limit: 20 }),
  })
  const impactQuery = useQuery({
    queryKey: ['intelligence', 'impact'],
    queryFn: () => intelligenceApi.impact(15),
  })
  const timelineQuery = useQuery({
    queryKey: ['intelligence', 'news', 'timeline'],
    queryFn: () => intelligenceApi.newsTimeline({ limit: 50 }),
  })

  const summaryFor = (newsEventId: string) => timelineQuery.data?.find((e) => e.id === newsEventId)?.summary

  return (
    <div className="mx-auto max-w-5xl space-y-10 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          News Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">
          Not a news feed — news, interpreted
        </h1>
      </div>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <Newspaper className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">Latest news</p>
        </div>

        {articlesQuery.isPending && (
          <div className="grid gap-4 sm:grid-cols-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </div>
        )}
        {articlesQuery.isError && <ErrorState error={articlesQuery.error} onRetry={() => void articlesQuery.refetch()} />}
        {articlesQuery.data && articlesQuery.data.length === 0 && (
          <EmptyState icon={Newspaper} title="No news yet" description="Nothing has come through News Intelligence yet." />
        )}
        {articlesQuery.data && articlesQuery.data.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            {articlesQuery.data.map((article) => (
              <Card key={article.id} className="flex flex-col gap-2 p-4">
                <p className="font-mono text-[11px] text-text-muted">
                  {new Date(article.published_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                </p>
                <p className="font-display text-sm font-semibold leading-snug text-text-primary">{article.title}</p>
                <a
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 text-xs font-medium text-accent-primary hover:text-accent-primary-hover"
                >
                  Read original source →
                </a>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-4 flex items-center gap-2">
          <TrendingUp className="size-4 text-accent-primary" aria-hidden="true" />
          <p className="text-sm font-medium text-text-primary">News impact</p>
        </div>

        {impactQuery.isPending && (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        )}
        {impactQuery.isError && <ErrorState error={impactQuery.error} onRetry={() => void impactQuery.refetch()} />}
        {impactQuery.data && impactQuery.data.length === 0 && (
          <EmptyState title="No scored impact yet" description="TitanIQ hasn't scored any news events for impact yet." />
        )}
        {impactQuery.data && impactQuery.data.length > 0 && (
          <div className="space-y-3">
            {impactQuery.data.map((score) => {
              const affected = [...score.affected_teams, ...score.affected_players, ...score.affected_competitions]
              return (
              <Card key={score.id} className="flex items-center gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-text-primary">
                    {summaryFor(score.news_event_id) ?? (affected.length > 0 ? `Event affecting ${affected[0]}` : 'Scored news event')}
                  </p>
                  {affected.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {affected.slice(0, 4).map((ref) => (
                        <Tag key={ref}>{ref}</Tag>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex w-28 shrink-0 items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                    <div
                      className="h-full rounded-full bg-accent-secondary"
                      style={{ width: `${Math.min(100, Math.max(0, score.impact_score) * 100)}%` }}
                    />
                  </div>
                  <span className="font-mono text-xs tabular-nums text-text-secondary">{score.impact_score.toFixed(2)}</span>
                </div>
              </Card>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
