import { useQuery } from '@tanstack/react-query'
import { sportsApi } from '@/lib/api/sports'

/** Same 48h staleness ceiling `PredictionConsistencyGate` (backend) and `prediction-intelligence.tsx`
 * (frontend) already use — one real threshold reused everywhere, not a third arbitrary number. */
const STALE_AFTER_MS = 48 * 60 * 60 * 1000

export type FreshnessStatus = 'loading' | 'unavailable' | 'fresh' | 'stale'

export interface DataFreshness {
  status: FreshnessStatus
  lastSyncedAt: string | null
  label: string
}

/**
 * Real "when did TitanIQ last pull data from a provider" reading (`sportsApi.syncStatus`) — this
 * is a platform-wide signal (one sync pipeline, not one per competition/player), so every page
 * using this hook is reporting the same real timestamp, never a per-entity value that doesn't
 * exist. Never claims "Live" — this reflects batch sync freshness, not a streaming connection.
 */
export function useDataFreshness(): DataFreshness {
  const query = useQuery({
    queryKey: ['sports', 'sync-status'],
    queryFn: () => sportsApi.syncStatus(),
    staleTime: 5 * 60 * 1000,
  })

  if (query.isPending) return { status: 'loading', lastSyncedAt: null, label: 'Checking data freshness…' }

  const lastSyncedAt = query.data?.last_synced_at ?? null
  if (!lastSyncedAt) return { status: 'unavailable', lastSyncedAt: null, label: 'Data freshness unavailable' }

  const ageMs = Date.now() - new Date(lastSyncedAt).getTime()
  const stale = ageMs > STALE_AFTER_MS
  const label = stale ? 'Data delayed' : `Updated ${relativeTime(lastSyncedAt)}`
  return { status: stale ? 'stale' : 'fresh', lastSyncedAt, label }
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}
