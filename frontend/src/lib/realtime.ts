import type { RealtimePostgresChangesPayload } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'

/**
 * Supabase Realtime publication tables (backend audit, alembic/versions/0014 + 0019) — 12 tables
 * total across two migrations. docs/rls.md §8 only documents migration 0014's 8; the 4 more from
 * 0019 are included here since they're live on the publication regardless of that doc gap.
 */
export const REALTIME_TABLES = {
  matches: { schema: 'sports', table: 'matches' },
  matchEvents: { schema: 'sports', table: 'match_events' },
  providerHealthState: { schema: 'admin', table: 'provider_health_state' },
  providerIncidents: { schema: 'admin', table: 'provider_incidents' },
  syncRuns: { schema: 'ingestion', table: 'sync_runs' },
  sessions: { schema: 'identity', table: 'sessions' },
  securityEvents: { schema: 'identity', table: 'security_events' },
  webhookDeliveries: { schema: 'webhooks', table: 'webhook_deliveries' },
  predictions: { schema: 'predictions', table: 'predictions' },
  predictionMarkets: { schema: 'predictions', table: 'prediction_markets' },
  predictionAudits: { schema: 'predictions', table: 'prediction_audits' },
  featureValuesOffline: { schema: 'features', table: 'feature_values_offline' },
} as const

export type RealtimeTableKey = keyof typeof REALTIME_TABLES

/**
 * Subscribes to Postgres changes on one published table. Returns an unsubscribe function — call
 * it on component unmount (or let a React Query-driven hook wrap this, see
 * src/lib/hooks/use-realtime-table.ts) to avoid leaking channels across route changes.
 */
export function subscribeToTable<Row extends Record<string, unknown> = Record<string, unknown>>(
  key: RealtimeTableKey,
  onChange: (payload: RealtimePostgresChangesPayload<Row>) => void,
  filter?: string,
): () => void {
  const { schema, table } = REALTIME_TABLES[key]
  const channelName = filter ? `${schema}:${table}:${filter}` : `${schema}:${table}`

  const channel = supabase
    .channel(channelName)
    .on(
      'postgres_changes',
      { event: '*', schema, table, ...(filter ? { filter } : {}) },
      (payload: RealtimePostgresChangesPayload<Row>) => onChange(payload),
    )
    .subscribe()

  return () => {
    void supabase.removeChannel(channel)
  }
}
