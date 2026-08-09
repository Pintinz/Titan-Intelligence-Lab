import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Activity, Bell, Layers } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useAlerts, useUnreadAlertCount } from '@/lib/hooks/use-alerts'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { ErrorState } from '@/components/ui/error-state'
import { CDButton } from '@/components/command-deck/primitives/button'
import { MissionSection, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import { AlertTimelineItem } from '@/components/command-deck/alerts/alert-timeline-item'
import { EventTypeRegistry } from '@/components/command-deck/alerts/event-type-registry'
import type { AlertEventDto, AlertType, FixtureSummaryDto, TeamSummaryDto } from '@/lib/api/types'

function sportSlugFor(sportCode: string | null | undefined): string {
  return (SPORT_SLUGS.find((s) => s.code === sportCode)?.slug ?? 'football').replace('_', '-')
}

const FILTERS: Array<{ key: 'all' | AlertType; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'kickoff', label: 'Kickoff' },
  { key: 'final_result', label: 'Final' },
  { key: 'prediction_changed', label: 'Prediction changes' },
]

function dateGroupLabel(dateStr: string | null): string {
  if (!dateStr) return 'Earlier'
  const date = new Date(dateStr)
  const now = new Date()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const sameDay = (a: Date, b: Date) => a.toDateString() === b.toDateString()
  if (sameDay(date, now)) return 'Today'
  if (sameDay(date, yesterday)) return 'Yesterday'
  return 'Earlier'
}

function hrefFor(fixture: FixtureSummaryDto | undefined, team: TeamSummaryDto | undefined): string | null {
  if (fixture) return `/app/${sportSlugFor(fixture.sport_code)}/matches/${fixture.id}`
  if (team) return `/app/${sportSlugFor(team.sport_code)}/teams/${team.id}`
  return null
}

export default function AlertsPage() {
  const { data, isPending, isError, error, refetch, markRead } = useAlerts()
  const unreadQuery = useUnreadAlertCount()
  const watchlist = useWatchlist()
  const [filter, setFilter] = useState<'all' | AlertType>('all')

  const events = data ?? []

  const fixtureRefs = useMemo(
    () => Array.from(new Set(events.filter((e) => e.entity_type === 'fixture').map((e) => e.entity_ref))),
    [events],
  )
  const teamRefs = useMemo(
    () => Array.from(new Set(events.filter((e) => e.entity_type === 'team').map((e) => e.entity_ref))),
    [events],
  )

  const fixtureQueries = useQueries({
    queries: fixtureRefs.map((id) => ({ queryKey: ['sports', 'fixture', id], queryFn: () => sportsApi.getFixture(id) })),
  })
  const teamQueries = useQueries({
    queries: teamRefs.map((id) => ({ queryKey: ['sports', 'teams', id], queryFn: () => sportsApi.getTeam(id) })),
  })

  const fixtureById = new Map(fixtureRefs.map((id, i) => [id, fixtureQueries[i].data]))
  const teamById = new Map(teamRefs.map((id, i) => [id, teamQueries[i].data]))

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: events.length }
    for (const e of events) c[e.alert_type] = (c[e.alert_type] ?? 0) + 1
    return c
  }, [events])

  const filtered = filter === 'all' ? events : events.filter((e) => e.alert_type === filter)

  const grouped = useMemo(() => {
    const groups = new Map<string, AlertEventDto[]>()
    for (const event of filtered) {
      const key = dateGroupLabel(event.created_at)
      const list = groups.get(key) ?? []
      list.push(event)
      groups.set(key, list)
    }
    const order = ['Today', 'Yesterday', 'Earlier']
    return order.filter((key) => groups.has(key)).map((key) => [key, groups.get(key)!] as const)
  }, [filtered])

  const latestEvent = events[0] ?? null
  const trackingCount = watchlist.data?.length

  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: 'var(--cd-accent)' }}>
            Alerts
          </p>
          <h2 className="mt-1 font-[var(--cd-font-display)] text-[26px] font-semibold tracking-[-0.01em] sm:text-[30px]" style={{ color: 'var(--cd-text-primary)' }}>
            Intelligence Alerts
          </h2>
          <p className="mt-1 max-w-xl font-[var(--cd-font-body)] text-[13.5px]" style={{ color: 'var(--cd-text-muted)' }}>
            Monitor meaningful changes across the matches, teams, and predictions you follow.
          </p>
        </div>
        <CDButton variant="primary" href="/app/watchlist">
          Manage Watchlist
        </CDButton>
      </div>

      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-3 sm:overflow-visible">
        <StatusTile label="Unread" value={unreadQuery.isPending ? null : (unreadQuery.data ?? 0)} />
        <StatusTile label="Tracking" value={trackingCount !== undefined ? `${trackingCount} ${trackingCount === 1 ? 'entity' : 'entities'}` : null} />
        <StatusTile
          label="Last event"
          value={latestEvent?.created_at ? new Date(latestEvent.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'No events yet'}
        />
      </div>

      {events.length > 0 && (
        <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          {FILTERS.filter((f) => f.key === 'all' || (counts[f.key] ?? 0) > 0).map((f) => {
            const active = filter === f.key
            return (
              <button
                key={f.key}
                type="button"
                onClick={() => setFilter(f.key)}
                className="shrink-0 rounded-[var(--cd-radius-md)] px-3 py-1.5 font-[var(--cd-font-body)] text-[12.5px] font-medium transition-colors duration-[var(--cd-motion-snap)]"
                style={{
                  backgroundColor: active ? 'var(--cd-accent-muted)' : 'var(--cd-surface-1)',
                  border: `1px solid ${active ? 'var(--cd-accent-strong)' : 'var(--cd-border-default)'}`,
                  color: active ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
                }}
              >
                {f.label}
                {counts[f.key] ? ` (${counts[f.key]})` : ''}
              </button>
            )
          })}
        </div>
      )}

      <MissionSection title="Recent Intelligence" icon={<Activity className="size-4" aria-hidden="true" />}>
        {isPending && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-20 animate-pulse rounded-[var(--cd-radius-lg)] motion-reduce:animate-none" style={{ background: 'var(--cd-surface-1)' }} />
            ))}
          </div>
        )}

        {!isPending && events.length === 0 && (
          <MissionEmptyState
            icon={Bell}
            title="Intelligence stream clear"
            description="Nothing needs your attention yet. Follow a match or team and TitanIQ will surface meaningful changes here — kickoffs, final results, and published prediction changes."
            actionLabel="Explore matches"
            actionHref="/app/football/matches"
            secondaryActionLabel="Open watchlist"
            secondaryActionHref="/app/watchlist"
          />
        )}

        {!isPending && events.length > 0 && filtered.length === 0 && (
          <p className="rounded-[var(--cd-radius-lg)] border p-6 text-center font-[var(--cd-font-body)] text-[13px]" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
            No alerts match this filter.
          </p>
        )}

        {!isPending && grouped.length > 0 && (
          <div className="space-y-5">
            {grouped.map(([label, items]) => (
              <div key={label}>
                <p className="font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.08em]" style={{ color: 'var(--cd-text-muted)' }}>
                  {label}
                </p>
                <ul className="mt-2 space-y-2">
                  {items.map((event) => (
                    <AlertTimelineItem
                      key={event.id}
                      event={event}
                      fixture={fixtureById.get(event.entity_ref)}
                      team={teamById.get(event.entity_ref)}
                      href={hrefFor(fixtureById.get(event.entity_ref), teamById.get(event.entity_ref))}
                      onMarkRead={() => markRead(event.id)}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </MissionSection>

      <MissionSection
        title="Event Types"
        icon={<Layers className="size-4" aria-hidden="true" />}
        subtitle="Some intelligence events are planned but are not currently connected to a live data trigger."
      >
        <EventTypeRegistry />
      </MissionSection>
    </div>
  )
}

function StatusTile({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="min-w-[8rem] shrink-0 rounded-[var(--cd-radius-lg)] px-4 py-3" style={{ backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-default)' }}>
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
      {value === null ? (
        <span className="mt-1 inline-block h-7 w-10 animate-pulse rounded motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
      ) : (
        <p className="mt-1 truncate font-[var(--cd-font-tabular)] text-[19px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
          {value}
        </p>
      )}
    </div>
  )
}
