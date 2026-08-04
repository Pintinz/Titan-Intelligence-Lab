import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Newspaper, TrendingUp, Building, Search, Rss, RefreshCw } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { adminPlatformApi } from '@/lib/api/admin-platform'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { OpsPageHeader, SectionCard, MetricTile, BackendPendingState } from '@/components/ops/ops-primitives'
import { toast } from '@/stores/toast-store'

function NewsSourcesPanel() {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const queryClient = useQueryClient()

  const sourcesQuery = useQuery({ queryKey: ['admin', 'news', 'sources'], queryFn: () => adminPlatformApi.listNewsSources() })

  const invalidateAfterSync = () => {
    void queryClient.invalidateQueries({ queryKey: ['intelligence', 'news'] })
    void queryClient.invalidateQueries({ queryKey: ['intelligence', 'analytics'] })
  }

  const register = useMutation({
    mutationFn: () => adminPlatformApi.registerNewsSource({ name, url, source_type: 'rss_feed' }),
    onSuccess: (source) => {
      toast.success('Source registered', source.name)
      setName('')
      setUrl('')
      void queryClient.invalidateQueries({ queryKey: ['admin', 'news', 'sources'] })
    },
    onError: (error) => toast.danger('Could not register source', error instanceof Error ? error.message : undefined),
  })

  const sync = useMutation({
    mutationFn: (sourceId: string) => adminPlatformApi.triggerNewsSync(sourceId),
    onSuccess: (run) => {
      const created = run.items_created as number
      const fetched = run.items_fetched as number
      toast.success('Sync complete', `${created} new / ${fetched} fetched`)
      invalidateAfterSync()
    },
    onError: (error) => toast.danger('Sync failed', error instanceof Error ? error.message : undefined),
  })

  return (
    <SectionCard
      icon={Rss}
      title="News sources"
      description="Register a real RSS/Atom feed and trigger ingestion — articles land in the feed below immediately."
    >
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <Label htmlFor="source-name">Name</Label>
          <Input id="source-name" placeholder="BBC Sport" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 w-44" />
        </div>
        <div>
          <Label htmlFor="source-url">Feed URL</Label>
          <Input
            id="source-url"
            placeholder="https://feeds.bbci.co.uk/sport/football/rss.xml"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            className="mt-1.5 w-80"
          />
        </div>
        <Button onClick={() => register.mutate()} disabled={!name || !url || register.isPending} className="gap-1">
          {register.isPending ? 'Registering…' : 'Register'}
        </Button>
      </div>

      <div className="mt-4 border-t border-border-subtle pt-4">
        {sourcesQuery.isPending && <Skeleton className="h-16" />}
        {sourcesQuery.isError && <ErrorState error={sourcesQuery.error} onRetry={() => void sourcesQuery.refetch()} />}
        {sourcesQuery.data && sourcesQuery.data.length === 0 && (
          <p className="text-sm text-text-muted">No sources registered yet — add a real RSS feed above to start ingesting.</p>
        )}
        {sourcesQuery.data && sourcesQuery.data.length > 0 && (
          <ul className="space-y-1.5">
            {sourcesQuery.data.map((source) => (
              <li key={source.id} className="flex items-center justify-between gap-3 rounded-md border border-border-default p-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm text-text-primary">{source.name}</p>
                  <p className="truncate font-mono text-[11px] text-text-muted">{source.url}</p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => sync.mutate(source.id)}
                  disabled={sync.isPending}
                  className="shrink-0 gap-1"
                >
                  <RefreshCw className="size-3.5" />
                  {sync.isPending ? 'Syncing…' : 'Sync now'}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </SectionCard>
  )
}

export default function NewsIntelligenceAdminPage() {
  const [sourceId, setSourceId] = useState('')
  const [lookupSourceId, setLookupSourceId] = useState('')

  const analyticsQuery = useQuery({ queryKey: ['intelligence', 'analytics'], queryFn: () => intelligenceApi.analytics() })
  const articlesQuery = useQuery({ queryKey: ['intelligence', 'news', 'recent'], queryFn: () => intelligenceApi.searchNews({ limit: 15 }) })
  const timelineQuery = useQuery({ queryKey: ['intelligence', 'news', 'timeline'], queryFn: () => intelligenceApi.newsTimeline({ limit: 15 }) })
  const impactQuery = useQuery({ queryKey: ['intelligence', 'impact'], queryFn: () => intelligenceApi.impact(15) })
  const reliabilityQuery = useQuery({
    queryKey: ['intelligence', 'source-reliability', lookupSourceId],
    queryFn: () => intelligenceApi.sourceReliability(lookupSourceId),
    enabled: !!lookupSourceId,
    retry: false,
  })

  const analytics = analyticsQuery.data

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Intelligence"
        title="News Intelligence Administration"
        description="Ingestion volume, processing pipeline health, prediction impact, and source reliability for every article TitanIQ processes."
      />

      <NewsSourcesPanel />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile icon={Newspaper} label="Articles ingested" value={analyticsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((analytics?.article_count as number | undefined) ?? '—')} />
        <MetricTile icon={TrendingUp} label="Recent ingestion runs" value={analyticsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((analytics?.news_ingestion_runs_recent as number | undefined) ?? '—')} />
        <MetricTile icon={Search} label="Gemini calls" value={analyticsQuery.isPending ? <Skeleton className="h-6 w-8" /> : ((analytics?.gemini_call_count as number | undefined) ?? '—')} />
        <MetricTile
          icon={Building}
          label="Duplicate rate"
          value={analyticsQuery.isPending ? <Skeleton className="h-6 w-8" /> : (typeof analytics?.news_duplicate_rate === 'number' ? `${(analytics.news_duplicate_rate * 100).toFixed(1)}%` : '—')}
          tone={typeof analytics?.news_duplicate_rate === 'number' && analytics.news_duplicate_rate > 0.1 ? 'warning' : 'default'}
        />
      </div>

      <SectionCard title="Pipeline & source analytics" description="Full raw analytics payload from the intelligence pipeline.">
        {analyticsQuery.isPending && <Skeleton className="h-20" />}
        {analyticsQuery.isError && <ErrorState error={analyticsQuery.error} onRetry={() => void analyticsQuery.refetch()} />}
        {analytics && <KeyValueGrid data={analytics} />}
      </SectionCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SectionCard icon={Newspaper} title="Recently ingested articles">
          {articlesQuery.isPending && <Skeleton className="h-40" />}
          {articlesQuery.isError && <ErrorState error={articlesQuery.error} onRetry={() => void articlesQuery.refetch()} />}
          {articlesQuery.data && articlesQuery.data.length === 0 && <EmptyState variant="minimal" title="No articles yet" />}
          {articlesQuery.data && articlesQuery.data.length > 0 && (
            <ul className="space-y-2">
              {articlesQuery.data.map((a) => (
                <li key={a.id} className="rounded-md border border-border-subtle p-2.5">
                  <p className="truncate text-sm text-text-primary">{a.title}</p>
                  <div className="mt-1 flex items-center justify-between">
                    <p className="font-mono text-[11px] text-text-muted">{new Date(a.published_at).toLocaleDateString()}</p>
                    <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-accent-primary hover:text-accent-primary-hover">
                      Source →
                    </a>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>

        <SectionCard icon={TrendingUp} title="News event timeline">
          {timelineQuery.isPending && <Skeleton className="h-40" />}
          {timelineQuery.isError && <ErrorState error={timelineQuery.error} onRetry={() => void timelineQuery.refetch()} />}
          {timelineQuery.data && timelineQuery.data.length === 0 && <EmptyState variant="minimal" title="No events yet" />}
          {timelineQuery.data && timelineQuery.data.length > 0 && (
            <ul className="space-y-2">
              {timelineQuery.data.map((event) => (
                <li key={event.id} className="rounded-md border border-border-subtle p-2.5">
                  <p className="truncate text-sm text-text-primary">{event.summary}</p>
                  <p className="mt-1 font-mono text-[11px] text-text-muted">{event.event_type} · {new Date(event.occurred_at).toLocaleString()}</p>
                </li>
              ))}
            </ul>
          )}
        </SectionCard>
      </div>

      <SectionCard title="Prediction & confidence impact" description="Recent news events scored for how much they moved a prediction or its confidence.">
        {impactQuery.isPending && <Skeleton className="h-24" />}
        {impactQuery.isError && <ErrorState error={impactQuery.error} onRetry={() => void impactQuery.refetch()} />}
        {impactQuery.data && impactQuery.data.length === 0 && <EmptyState variant="minimal" title="No impact scores recorded yet" />}
        {impactQuery.data && impactQuery.data.length > 0 && (
          <ul className="space-y-2">
            {impactQuery.data.map((score) => {
              const affected = [...score.affected_teams, ...score.affected_players, ...score.affected_competitions]
              return (
              <li key={score.id} className="flex items-center justify-between gap-3 rounded-md border border-border-subtle p-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm text-text-primary">{affected.length > 0 ? affected.join(', ') : `Event ${score.news_event_id}`}</p>
                </div>
                <span className="shrink-0 font-mono text-sm tabular-nums text-accent-primary">{score.impact_score.toFixed(2)}</span>
              </li>
              )
            })}
          </ul>
        )}
      </SectionCard>

      <SectionCard icon={Building} title="Source reliability lookup" description="Look up a source's historical reliability score by its source ID.">
        <div className="flex gap-2">
          <Input placeholder="source id" value={sourceId} onChange={(e) => setSourceId(e.target.value)} className="max-w-xs" />
          <Button size="sm" onClick={() => setLookupSourceId(sourceId)} disabled={!sourceId}>Look up</Button>
        </div>
        {reliabilityQuery.isPending && lookupSourceId && <Skeleton className="mt-3 h-12" />}
        {reliabilityQuery.isError && lookupSourceId && (
          <p className="mt-3 text-sm text-text-muted">No reliability record found for "{lookupSourceId}".</p>
        )}
        {reliabilityQuery.data && (
          <div className="mt-3">
            <KeyValueGrid data={reliabilityQuery.data as unknown as Record<string, unknown>} />
          </div>
        )}
      </SectionCard>

      <SectionCard title="Not yet available">
        <BackendPendingState
          title="Ingestion queue depth, duplicate-detection detail, and per-source health dashboard"
          description="Aggregate duplicate rate and article counts are available via analytics above, but a live processing-queue view, a per-article duplicate-match explanation, and a source directory (to browse rather than look up reliability by known ID) are not yet exposed as endpoints."
          recommendedEndpoint="GET /api/v1/admin/intelligence/sources · GET /api/v1/admin/intelligence/queue"
        />
      </SectionCard>
    </div>
  )
}
