import { Bell, PlayCircle, FlagTriangleRight, TrendingUp, Check } from 'lucide-react'
import { useAlerts } from '@/lib/hooks/use-alerts'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityButton } from '@/components/infinity/primitives/button'
import type { AlertEventDto, AlertType } from '@/lib/api/types'

const ALERT_TYPE_ICON: Record<AlertType, typeof Bell> = {
  kickoff: PlayCircle,
  final_result: FlagTriangleRight,
  prediction_changed: TrendingUp,
}

const ALERT_TYPE_LABEL: Record<AlertType, string> = {
  kickoff: 'Kickoff',
  final_result: 'Final result',
  prediction_changed: 'Prediction changed',
}

const NOT_YET_AVAILABLE = [
  { label: 'Goal', description: 'Needs live match-event ingestion, which nothing in the pipeline populates yet.' },
  { label: 'Lineups', description: 'No lineup data source is wired into any provider adapter yet.' },
  { label: 'Injuries', description: 'No injury data source is wired into any provider adapter yet.' },
  { label: 'Breaking News', description: "No impact-scored news signal exists yet to decide what's alert-worthy." },
]

export default function AlertsPage() {
  const { data, isPending, isError, error, refetch, markRead } = useAlerts()

  return (
    <div className="space-y-8">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Alerts</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          What's happening with what you follow
        </h2>
        <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">
          Real alerts only — fired when a match you're watching kicks off or finishes, or when its
          prediction changes.
        </p>
      </div>

      {isPending && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-16" />
          ))}
        </div>
      )}

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {data && data.length === 0 && (
        <InfinityEmptyState
          icon={Bell}
          title="Nothing yet"
          description="Follow a match or team from its card — you'll see kickoff, final result, and prediction-change alerts here as they happen."
        />
      )}

      {data && data.length > 0 && (
        <ul className="space-y-2">
          {data.map((event) => (
            <AlertRow key={event.id} event={event} onMarkRead={() => markRead(event.id)} />
          ))}
        </ul>
      )}

      <div>
        <InfinityLabel>Not yet available</InfinityLabel>
        <p className="mt-1 font-infinity-body text-[12px] text-infinity-text-secondary">
          These alert types are part of the plan but have no real trigger wired yet — shown here
          instead of silently missing.
        </p>
        <ul className="mt-3 space-y-2">
          {NOT_YET_AVAILABLE.map((item) => (
            <li
              key={item.label}
              className="rounded-infinity-md border border-dashed border-infinity-border-default p-3"
            >
              <p className="font-infinity-body text-[12px] font-medium text-infinity-text-secondary">{item.label}</p>
              <p className="mt-0.5 font-infinity-body text-[11px] text-infinity-text-muted">{item.description}</p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function AlertRow({ event, onMarkRead }: { event: AlertEventDto; onMarkRead: () => void }) {
  const Icon = ALERT_TYPE_ICON[event.alert_type]
  const unread = event.read_at === null
  return (
    <li
      className={`flex items-start gap-3 rounded-infinity-md border p-3 ${
        unread ? 'border-infinity-signal-muted bg-infinity-signal-muted/20' : 'border-infinity-border-hairline'
      }`}
    >
      <Icon className="mt-0.5 size-4 shrink-0 text-infinity-signal" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <InfinityLabel>{ALERT_TYPE_LABEL[event.alert_type]}</InfinityLabel>
          {event.created_at && (
            <span className="font-infinity-mono text-[10px] text-infinity-text-muted">
              {new Date(event.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
            </span>
          )}
        </div>
        <p className="mt-1 font-infinity-body text-[13px] font-medium text-infinity-text-primary">{event.title}</p>
        <p className="mt-0.5 font-infinity-body text-[12px] text-infinity-text-secondary">{event.body}</p>
      </div>
      {unread && (
        <InfinityButton type="button" variant="ghost" size="sm" onClick={onMarkRead} aria-label="Mark as read">
          <Check className="size-3.5" aria-hidden="true" />
        </InfinityButton>
      )}
    </li>
  )
}
