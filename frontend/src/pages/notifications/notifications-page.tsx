import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { EmptyState } from '@/components/ui/empty-state'
import { Timeline, type TimelineEntry } from '@/components/domain/timeline'
import { subscribeToTable, type RealtimeTableKey } from '@/lib/realtime'

const WATCHED_TABLES: Array<{ key: RealtimeTableKey; label: string; tone: TimelineEntry['tone'] }> = [
  { key: 'predictions', label: 'Prediction updated', tone: 'info' },
  { key: 'predictionAudits', label: 'Prediction audit event', tone: 'neutral' },
  { key: 'syncRuns', label: 'Ingestion sync run', tone: 'neutral' },
  { key: 'providerIncidents', label: 'Provider incident', tone: 'danger' },
]

/**
 * There is no backend "notifications" entity/endpoint — M6 built audit logs and Session/Security
 * Intelligence, not a generic notification feed. This page is the honest alternative: it turns
 * the Realtime-published table changes (already live per docs/rls.md §8) into a session-local
 * activity feed, rather than faking a notifications API that doesn't exist.
 */
export default function NotificationsPage() {
  const [entries, setEntries] = useState<TimelineEntry[]>([])

  useEffect(() => {
    const unsubscribes = WATCHED_TABLES.map(({ key, label, tone }) =>
      subscribeToTable(key, (payload) => {
        setEntries((prev) => [
          {
            id: `${key}-${Date.now()}-${Math.random()}`,
            timestamp: new Date().toISOString(),
            title: label,
            description: payload.eventType,
            tone,
          },
          ...prev,
        ].slice(0, 100))
      }),
    )
    return () => unsubscribes.forEach((unsub) => unsub())
  }, [])

  return (
    <div className="flex flex-col gap-6 p-6">
      <div>
        <Breadcrumbs items={[{ label: 'Dashboard', to: '/app' }, { label: 'Notifications' }]} />
        <h1 className="mt-2 font-display text-2xl font-semibold text-text-primary">Notifications</h1>
        <p className="mt-1 text-sm text-text-secondary">Live activity — this session only.</p>
      </div>

      {entries.length === 0 ? (
        <EmptyState icon={<Bell className="h-6 w-6" />} title="No activity yet" description="Live events will appear here as they happen." />
      ) : (
        <Timeline entries={entries} />
      )}
    </div>
  )
}
