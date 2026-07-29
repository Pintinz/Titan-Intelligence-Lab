import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { StatusDot } from '@/components/ui/status-dot'
import { subscribeToTable, type RealtimeTableKey } from '@/lib/realtime'

const WATCHED_TABLES: Array<{ key: RealtimeTableKey; label: string; tone: 'info' | 'danger' | 'neutral' }> = [
  { key: 'predictions', label: 'Prediction updated', tone: 'info' },
  { key: 'providerIncidents', label: 'Provider incident', tone: 'danger' },
  { key: 'syncRuns', label: 'Ingestion sync run', tone: 'neutral' },
]

interface Entry {
  id: string
  label: string
  tone: 'info' | 'danger' | 'neutral'
  timestamp: string
}

/**
 * Same realtime-table source as pages/notifications/notifications-page.tsx — TitanIQ has no
 * persisted notifications API (M6 shipped audit logs and Session/Security Intelligence, not a
 * generic notification feed), so this stays session-local rather than faking a backend feed.
 */
export function NotificationCenter() {
  const [entries, setEntries] = useState<Entry[]>([])

  useEffect(() => {
    const unsubscribes = WATCHED_TABLES.map(({ key, label, tone }) =>
      subscribeToTable(key, () => {
        setEntries((prev) => [{ id: `${key}-${prev.length}-${Date.now()}`, label, tone, timestamp: new Date().toISOString() }, ...prev].slice(0, 8))
      }),
    )
    return () => unsubscribes.forEach((unsub) => unsub())
  }, [])

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="h-4 w-4" />
          {entries.length > 0 && (
            <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-accent-primary" aria-hidden="true" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="p-0">
        <div className="border-b border-border-subtle px-4 py-3">
          <p className="text-sm font-medium text-text-primary">Live activity</p>
          <p className="text-xs text-text-muted">This session only — not a persisted history.</p>
        </div>
        <div className="max-h-72 overflow-y-auto p-2">
          {entries.length === 0 ? (
            <p className="px-2 py-4 text-center text-sm text-text-muted">No activity yet.</p>
          ) : (
            entries.map((entry) => (
              <div key={entry.id} className="flex items-start gap-2 rounded-md px-2 py-2 text-sm hover:bg-bg-secondary">
                <StatusDot tone={entry.tone === 'info' ? 'info' : entry.tone === 'danger' ? 'danger' : 'neutral'} className="mt-1.5" />
                <div>
                  <p className="text-text-primary">{entry.label}</p>
                  <p className="text-xs text-text-muted">{new Date(entry.timestamp).toLocaleTimeString()}</p>
                </div>
              </div>
            ))
          )}
        </div>
        <div className="border-t border-border-subtle p-2">
          <Button asChild variant="ghost" size="sm" className="w-full">
            <Link to="/app/notifications">View all activity</Link>
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
