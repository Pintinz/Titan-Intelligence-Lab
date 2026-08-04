import { api } from '@/lib/api/client'
import type { WatchlistEntityType, WatchlistEntryDto } from '@/lib/api/types'

export const watchlistApi = {
  list: (entityType?: WatchlistEntityType) =>
    api.get<WatchlistEntryDto[]>('/api/v1/watchlist', entityType ? { entity_type: entityType } : undefined),
  follow: (entityType: WatchlistEntityType, entityRef: string) =>
    api.post<WatchlistEntryDto>('/api/v1/watchlist', { entity_type: entityType, entity_ref: entityRef }),
  unfollow: (entryId: string) => api.delete<{ unfollowed: boolean }>(`/api/v1/watchlist/${entryId}`),
}
