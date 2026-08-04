import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageCircle, TrendingUp, Search } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'
import { OpsPageHeader, SectionCard, MetricTile, BackendPendingState } from '@/components/ops/ops-primitives'

export default function CommunityIntelligenceAdminPage() {
  const [entityRef, setEntityRef] = useState('')
  const [lookupRef, setLookupRef] = useState('')

  const topicsQuery = useQuery({ queryKey: ['intelligence', 'community-topics'], queryFn: () => intelligenceApi.communityTopics() })
  const sentimentQuery = useQuery({
    queryKey: ['intelligence', 'sentiment', lookupRef],
    queryFn: () => intelligenceApi.sentiment(lookupRef),
    enabled: !!lookupRef,
    retry: false,
  })

  const topics = topicsQuery.data ?? []
  const totalVolume = topics.reduce((sum, t) => sum + t.post_count, 0)
  const byPlatform = topics.reduce<Record<string, number>>((acc, t) => {
    acc[t.platform] = (acc[t.platform] ?? 0) + t.post_count
    return acc
  }, {})
  const maxVolume = Math.max(1, ...topics.map((t) => t.post_count))

  return (
    <div className="space-y-6">
      <OpsPageHeader
        eyebrow="Intelligence"
        title="Community Intelligence"
        description="Community signal volume, platform breakdown, sentiment, and trend across every tracked topic."
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricTile icon={MessageCircle} label="Tracked topics" value={topicsQuery.isPending ? <Skeleton className="h-6 w-8" /> : topics.length} />
        <MetricTile icon={TrendingUp} label="Total signal volume" value={topicsQuery.isPending ? <Skeleton className="h-6 w-8" /> : totalVolume.toLocaleString()} />
        {Object.entries(byPlatform).slice(0, 2).map(([platform, volume]) => (
          <MetricTile key={platform} icon={MessageCircle} label={`${platform} volume`} value={volume.toLocaleString()} />
        ))}
      </div>

      <SectionCard icon={TrendingUp} title="Topics by volume" description="All community topics currently tracked, ranked by signal volume.">
        {topicsQuery.isPending && (
          <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8" />)}</div>
        )}
        {topicsQuery.isError && <ErrorState error={topicsQuery.error} onRetry={() => void topicsQuery.refetch()} />}
        {topics.length === 0 && !topicsQuery.isPending && (
          <EmptyState
            variant="minimal"
            title="No community signal yet"
            description="No real social-media/forum adapter is connected — Community Intelligence is mock-only by design until a live platform provider exists (ADR-008), not just quiet today."
          />
        )}
        {topics.length > 0 && (
          <div className="space-y-2.5">
            {[...topics].sort((a, b) => b.post_count - a.post_count).map((topic) => (
              <div key={topic.id} className="flex items-center gap-3">
                <span className="w-32 shrink-0 truncate text-xs text-text-muted uppercase tracking-wide">{topic.platform}</span>
                <span className="w-40 shrink-0 truncate text-sm text-text-primary">{topic.topic_label}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                  <div
                    className={`h-full rounded-full ${topic.momentum !== null && topic.momentum < 0 ? 'bg-danger' : 'bg-accent-primary'}`}
                    style={{ width: `${(topic.post_count / maxVolume) * 100}%` }}
                  />
                </div>
                <span className="w-16 shrink-0 text-right font-mono text-xs text-text-muted">{topic.post_count.toLocaleString()}</span>
                {topic.momentum !== null && (
                  <span className={`w-14 shrink-0 text-right font-mono text-xs ${topic.momentum >= 0 ? 'text-success' : 'text-danger'}`}>
                    {topic.momentum >= 0 ? '+' : ''}{(topic.momentum * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </SectionCard>

      <SectionCard icon={Search} title="Sentiment lookup" description="Look up historical sentiment readings for a specific entity.">
        <div className="flex gap-2">
          <Input placeholder="entity ref (e.g. team:arsenal-fc)" value={entityRef} onChange={(e) => setEntityRef(e.target.value)} className="max-w-xs" />
          <Button size="sm" onClick={() => setLookupRef(entityRef)} disabled={!entityRef}>Look up</Button>
        </div>
        {sentimentQuery.isPending && lookupRef && <Skeleton className="mt-3 h-12" />}
        {sentimentQuery.isError && lookupRef && <p className="mt-3 text-sm text-text-muted">No sentiment history found for "{lookupRef}".</p>}
        {sentimentQuery.data && sentimentQuery.data.length === 0 && <p className="mt-3 text-sm text-text-muted">No readings recorded.</p>}
        {sentimentQuery.data && sentimentQuery.data.length > 0 && (
          <ul className="mt-3 space-y-1.5">
            {sentimentQuery.data.map((reading, i) => (
              <li key={i} className="flex items-center justify-between rounded border border-border-subtle px-2.5 py-1.5 text-xs">
                <span className="text-text-muted">{new Date(reading.computed_at).toLocaleString()}</span>
                <span className={reading.momentum !== null && reading.momentum < 0 ? 'text-danger' : 'text-success'}>
                  {reading.label}
                  {reading.momentum !== null && ` (${reading.momentum >= 0 ? '+' : ''}${(reading.momentum * 100).toFixed(0)}%`}
                  {reading.momentum !== null && `, confidence ${(reading.confidence * 100).toFixed(0)}%)`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard title="Not yet available">
        <BackendPendingState
          title="Spam detection status, bot detection, and per-platform (X/Reddit/forum) breakdowns"
          description="Community topics currently return an aggregate volume and sentiment score without a spam/bot filtering status field, and platform is a free-text value on each topic rather than a queryable dimension — both would need additive backend support."
          recommendedEndpoint="GET /api/v1/admin/community/moderation-status"
        />
      </SectionCard>
    </div>
  )
}
