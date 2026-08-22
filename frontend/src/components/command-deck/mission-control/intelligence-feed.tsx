import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, MessageCircle, Radar, Newspaper, Rss } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { MissionSection, MissionEmptyState } from './mission-section'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'

type FeedItem =
  | { kind: 'news'; id: string; headline: string; timestamp: string; href: string }
  | { kind: 'event'; id: string; headline: string; timestamp: string; confidence: number; affectedCount: number }
  | { kind: 'community'; id: string; headline: string; platform: string; postCount: number; momentum: number | null }

/** Each source type gets its own domain hue so a merged feed still reads at a glance which
 * kind of signal a row is — "Breaking" maps to `alerts` (urgency), not `news`, since it's a
 * distinct, time-sensitive category from a synced article. */
const KIND_META: Record<FeedItem['kind'], { label: string; icon: typeof Newspaper; domain: DomainKey }> = {
  news: { label: 'News', icon: Newspaper, domain: 'news' },
  event: { label: 'Breaking', icon: Radar, domain: 'alerts' },
  community: { label: 'Community', icon: MessageCircle, domain: 'community' },
}

/**
 * Intelligence Feed — merges three real, already-proven endpoints into one premium feed instead
 * of three separate sections. Each item keeps an honest source-type badge rather than being
 * forced into one fake homogeneous shape. No per-item "related match" name is shown: articles
 * carry no entity link at all, and resolving a news event's `affected_entity_refs` to real team/
 * competition names would mean an N+1 fetch per feed item — instead the real, already-free signal
 * (affected-entity count, community post count/momentum) stands in.
 */
export function IntelligenceFeed() {
  const newsQuery = useQuery({ queryKey: ['intelligence', 'news', 'mission-control'], queryFn: () => intelligenceApi.searchNews({ limit: 8 }) })
  const eventsQuery = useQuery({ queryKey: ['intelligence', 'timeline', 'mission-control'], queryFn: () => intelligenceApi.newsTimeline({ limit: 8 }) })
  const communityQuery = useQuery({ queryKey: ['intelligence', 'community', 'mission-control'], queryFn: () => intelligenceApi.communityTopics() })

  const isLoading = newsQuery.isPending || eventsQuery.isPending || communityQuery.isPending

  type TimeStampedFeedItem = Extract<FeedItem, { kind: 'news' } | { kind: 'event' }>

  const timeStamped: TimeStampedFeedItem[] = [
    ...(newsQuery.data ?? []).map((a): TimeStampedFeedItem => ({ kind: 'news', id: a.id, headline: a.title, timestamp: a.published_at, href: a.url })),
    ...(eventsQuery.data ?? []).map((e): TimeStampedFeedItem => ({
      kind: 'event',
      id: e.id,
      headline: e.summary,
      timestamp: e.occurred_at,
      confidence: e.confidence,
      affectedCount: e.affected_entity_refs.length,
    })),
  ].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

  const communityItems: FeedItem[] = (communityQuery.data ?? [])
    .slice()
    .sort((a, b) => (b.momentum ?? 0) - (a.momentum ?? 0))
    .map((t) => ({ kind: 'community', id: t.id, headline: t.topic_label, platform: t.platform, postCount: t.post_count, momentum: t.momentum }))

  // Real recency leads; community topics (no timestamp field to interleave by) fill remaining
  // slots up to the cap rather than crowding out fresher news/events.
  const CAP = 6
  const feed = [...timeStamped.slice(0, CAP - Math.min(2, communityItems.length)), ...communityItems.slice(0, 2)].slice(0, CAP)

  return (
    <MissionSection
      id="intelligence-feed"
      title="Intelligence Feed"
      subtitle="News, breaking events and community signal in one stream"
      icon={<Rss className="size-4" aria-hidden="true" />}
      viewAllHref={newsQuery.data && newsQuery.data.length > 0 ? '/app/context' : undefined}
    >
      {isLoading && (
        <div className="space-y-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="h-16 animate-pulse rounded-[var(--cd-radius-xl)]"
              style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)' }}
            />
          ))}
        </div>
      )}
      {!isLoading && feed.length === 0 && (
        <MissionEmptyState
          icon={Rss}
          title="TitanIQ is watching every synced source."
          description="Breaking intelligence, news, and community signal will appear here as soon as something surfaces."
        />
      )}
      {!isLoading && feed.length > 0 && (
        <ul className="space-y-2.5">
          {feed.map((item) => (
            <FeedRow key={`${item.kind}:${item.id}`} item={item} />
          ))}
        </ul>
      )}
    </MissionSection>
  )
}

function FeedRow({ item }: { item: FeedItem }) {
  const { label, icon: Icon, domain } = KIND_META[item.kind]
  const domainColor = CD_DOMAIN_COLOR_VAR[domain]
  const content = (
    <div
      className="group/row flex items-start gap-3 rounded-[var(--cd-radius-xl)] p-3.5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <span
        className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full transition-transform duration-[var(--cd-motion-base)] group-hover/row:scale-105"
        style={{ backgroundColor: domainTint(domain, 14), color: domainColor, boxShadow: `0 0 0 1px ${domainTint(domain, 32)} inset` }}
        aria-hidden="true"
      >
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]" style={{ color: domainColor }}>
            {label}
          </span>
          {item.kind !== 'community' && (
            <span className="font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              {new Date(item.timestamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
            </span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
          {item.headline}
        </p>
        <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          {item.kind === 'event' && `${Math.round(item.confidence * 100)}% confidence · ${item.affectedCount} entit${item.affectedCount === 1 ? 'y' : 'ies'} affected`}
          {item.kind === 'community' && `${item.platform} · ${item.postCount} posts${item.momentum !== null ? ` · momentum ${item.momentum.toFixed(1)}` : ''}`}
        </p>
      </div>
      {item.kind === 'news' && <ArrowUpRight className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />}
    </div>
  )

  if (item.kind === 'news') {
    return (
      <li>
        <a href={item.href} target="_blank" rel="noopener noreferrer">
          {content}
        </a>
      </li>
    )
  }
  return <li>{content}</li>
}
