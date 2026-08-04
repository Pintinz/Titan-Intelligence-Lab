import { useQuery } from '@tanstack/react-query'
import { MessageCircle } from 'lucide-react'
import { intelligenceApi } from '@/lib/api/intelligence'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { EmptyState } from '@/components/ui/empty-state'

/**
 * `intelligenceApi.communityTopics` has no sport/entity filter either (only `platform`), so
 * topics are matched client-side against this sport's own team names — same honest, best-effort
 * posture as the News Intelligence page. Topics that don't mention a known team are hidden rather
 * than shown unscoped, since an unfiltered global feed on a sport-specific page would be
 * misleading about what it's showing.
 */
export default function SportCommunityPage() {
  const sport = useSportParam()

  const teamsQuery = useQuery({
    queryKey: ['sports', 'teams', sport?.code],
    queryFn: () => sportsApi.listTeams(sport!.code),
    enabled: !!sport,
  })
  const topicsQuery = useQuery({
    queryKey: ['intelligence', 'community-topics'],
    queryFn: () => intelligenceApi.communityTopics(),
  })

  if (!sport) return null

  const isPending = teamsQuery.isPending || topicsQuery.isPending
  const isError = teamsQuery.isError || topicsQuery.isError
  const teamNames = (teamsQuery.data ?? []).flatMap((t) => [t.name, t.short_name])
  const topics = (topicsQuery.data ?? []).filter((topic) =>
    teamNames.some((name) => topic.topic_label.toLowerCase().includes(name.toLowerCase())),
  )
  const maxVolume = Math.max(1, ...topics.map((t) => t.post_count))

  return (
    <div className="space-y-6">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Community Pulse
        </p>
        <h2 className="mt-1 font-display text-lg font-semibold text-text-primary">{sport.label} community signal</h2>
      </div>

      {isPending && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={teamsQuery.error ?? topicsQuery.error} onRetry={() => { void teamsQuery.refetch(); void topicsQuery.refetch() }} />}

      {!isPending && !isError && topics.length === 0 && (topicsQuery.data ?? []).length === 0 && (
        <EmptyState
          icon={MessageCircle}
          title="No community signal yet"
          description="No real social-media or forum provider is connected yet — this isn't a quiet day, there's no live source configured to pull from."
        />
      )}
      {!isPending && !isError && topics.length === 0 && (topicsQuery.data ?? []).length > 0 && (
        <EmptyState
          icon={MessageCircle}
          title="No community signal yet"
          description={`No tracked topics mention a ${sport.label} team right now.`}
        />
      )}

      {topics.length > 0 && (
        <div className="space-y-3">
          {topics.map((topic) => (
            <div key={topic.id} className="flex items-center gap-4">
              <span className="w-48 shrink-0 truncate text-sm text-text-primary">{topic.topic_label}</span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                <div className="h-full rounded-full bg-accent-primary" style={{ width: `${(topic.post_count / maxVolume) * 100}%` }} />
              </div>
              <span className="w-16 shrink-0 text-right font-mono text-xs text-text-muted">{topic.post_count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
