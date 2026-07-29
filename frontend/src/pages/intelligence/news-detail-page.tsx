import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { intelligenceApi } from '@/lib/api/intelligence'

export default function NewsDetailPage() {
  const { articleId } = useParams<{ articleId: string }>()
  const [sentimentEntity, setSentimentEntity] = useState<string | null>(null)

  const articleQuery = useQuery({
    queryKey: ['intelligence', 'article', articleId],
    queryFn: () => intelligenceApi.getArticle(articleId!),
    enabled: Boolean(articleId),
  })

  const reliabilityQuery = useQuery({
    queryKey: ['intelligence', 'sourceReliability', articleQuery.data?.source_id],
    queryFn: () => intelligenceApi.sourceReliability(articleQuery.data!.source_id),
    enabled: Boolean(articleQuery.data),
    retry: false,
  })

  const sentimentQuery = useQuery({
    queryKey: ['intelligence', 'sentiment', sentimentEntity],
    queryFn: () => intelligenceApi.sentiment(sentimentEntity!),
    enabled: Boolean(sentimentEntity),
    retry: false,
  })

  const summaryQuery = useQuery({
    queryKey: ['intelligence', 'summary', sentimentEntity],
    queryFn: () => intelligenceApi.summary(sentimentEntity!, 'short'),
    enabled: Boolean(sentimentEntity),
    retry: false,
  })

  if (articleQuery.isLoading) return <PageLoader />
  if (articleQuery.isError || !articleQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this article." onRetry={() => articleQuery.refetch()} />
      </div>
    )
  }

  const article = articleQuery.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'News Center', to: '/app/news' }, { label: article.title }]} />
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">{article.title}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-xs text-text-muted">{new Date(article.published_at).toLocaleString()}</p>
            <a href={article.url} target="_blank" rel="noreferrer" className="text-sm text-accent-primary hover:underline">
              Read original source →
            </a>
            {article.entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {article.entities.map((entity) => (
                  <button key={entity} type="button" onClick={() => setSentimentEntity(entity)}>
                    <Badge variant={sentimentEntity === entity ? 'accent' : 'neutral'}>{entity}</Badge>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Source reliability</CardTitle>
            </CardHeader>
            <CardContent>
              {reliabilityQuery.isLoading && <Skeleton className="h-16" />}
              {reliabilityQuery.data ? (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-text-secondary">Reliability score</span>
                  <span className="font-mono text-text-primary">{Math.round(reliabilityQuery.data.reliability_score * 100)}%</span>
                </div>
              ) : (
                !reliabilityQuery.isLoading && <p className="text-sm text-text-muted">No reliability score recorded for this source yet.</p>
              )}
            </CardContent>
          </Card>

          {sentimentEntity && (
            <Card>
              <CardHeader>
                <CardTitle>Sentiment — {sentimentEntity}</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {sentimentQuery.isLoading && <Skeleton className="h-16" />}
                {sentimentQuery.data?.map((result, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs text-text-muted">{new Date(result.measured_at).toLocaleDateString()}</span>
                    <Badge variant={result.score > 0 ? 'success' : result.score < 0 ? 'danger' : 'neutral'}>
                      {result.score > 0 ? '+' : ''}
                      {result.score.toFixed(2)}
                    </Badge>
                  </div>
                ))}
                {sentimentQuery.data?.length === 0 && <p className="text-sm text-text-muted">No sentiment history for this entity.</p>}
              </CardContent>
            </Card>
          )}

          {sentimentEntity && (
            <Card>
              <CardHeader>
                <CardTitle>AI summary — {sentimentEntity}</CardTitle>
              </CardHeader>
              <CardContent>
                {summaryQuery.isLoading && <Skeleton className="h-16" />}
                {summaryQuery.data ? (
                  <p className="text-sm text-text-secondary">{summaryQuery.data.text}</p>
                ) : (
                  !summaryQuery.isLoading && <p className="text-sm text-text-muted">No AI summary generated for this entity yet.</p>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
