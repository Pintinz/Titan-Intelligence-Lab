import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { watchlistApi } from '@/lib/api/watchlist'
import type { WatchlistEntityType } from '@/lib/api/types'

const WATCHLIST_KEY = ['watchlist'] as const

/**
 * Single cached list of the current user's whole watchlist — cheap enough (one row per follow)
 * that every card checks membership against this instead of each card issuing its own
 * per-entity "am I following this" request.
 */
export function useWatchlist() {
  const queryClient = useQueryClient()
  const query = useQuery({ queryKey: WATCHLIST_KEY, queryFn: () => watchlistApi.list() })

  const follow = useMutation({
    mutationFn: (input: { entityType: WatchlistEntityType; entityRef: string }) =>
      watchlistApi.follow(input.entityType, input.entityRef),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY }),
  })

  const unfollow = useMutation({
    mutationFn: (entryId: string) => watchlistApi.unfollow(entryId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: WATCHLIST_KEY }),
  })

  function isFollowing(entityType: WatchlistEntityType, entityRef: string): boolean {
    return (query.data ?? []).some((e) => e.entity_type === entityType && e.entity_ref === entityRef)
  }

  function toggle(entityType: WatchlistEntityType, entityRef: string) {
    const existing = (query.data ?? []).find((e) => e.entity_type === entityType && e.entity_ref === entityRef)
    if (existing) {
      unfollow.mutate(existing.id)
    } else {
      follow.mutate({ entityType, entityRef })
    }
  }

  return { ...query, isFollowing, toggle }
}
