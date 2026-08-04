import { api } from '@/lib/api/client'
import type { AlertEventDto } from '@/lib/api/types'

export const alertsApi = {
  list: (opts: { unread_only?: boolean; limit?: number } = {}) =>
    api.get<AlertEventDto[]>('/api/v1/alerts', opts),
  unreadCount: () => api.get<{ count: number }>('/api/v1/alerts/unread-count'),
  markRead: (eventId: string) => api.post<{ read: boolean }>(`/api/v1/alerts/${eventId}/read`),
}
