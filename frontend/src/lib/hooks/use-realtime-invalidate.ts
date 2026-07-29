import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { subscribeToTable, type RealtimeTableKey } from '@/lib/realtime'

/**
 * Subscribes to a Realtime-published table for the lifetime of the calling component and
 * invalidates the given React Query key(s) on every change — refetch-on-change rather than
 * hand-patching the cache from the raw payload, since the payload is a raw row diff, not the
 * same shape the REST endpoint returns (feature_snapshot, confidence, explanation are nested/
 * computed there but flat columns here).
 */
export function useRealtimeInvalidate(table: RealtimeTableKey, queryKeys: unknown[][], filter?: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const unsubscribe = subscribeToTable(
      table,
      () => {
        for (const key of queryKeys) {
          void queryClient.invalidateQueries({ queryKey: key })
        }
      },
      filter,
    )
    return unsubscribe
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [table, filter, JSON.stringify(queryKeys)])
}
