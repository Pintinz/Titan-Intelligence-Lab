import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { alertsApi } from '@/lib/api/alerts'

const UNREAD_COUNT_KEY = ['alerts', 'unread-count'] as const

/** Polled rather than realtime — alert_events isn't on a Supabase Realtime publication (only the
 * tables actual live UI already depended on are), so a 30s poll is the honest signal available,
 * not a fabricated instant push. */
export function useUnreadAlertCount() {
  return useQuery({
    queryKey: UNREAD_COUNT_KEY,
    queryFn: () => alertsApi.unreadCount(),
    refetchInterval: 30_000,
    select: (data) => data.count,
  })
}

export function useAlerts(unreadOnly = false) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['alerts', 'list', unreadOnly],
    queryFn: () => alertsApi.list({ unread_only: unreadOnly, limit: 100 }),
  })

  const markRead = useMutation({
    mutationFn: (eventId: string) => alertsApi.markRead(eventId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })

  return { ...query, markRead: (eventId: string) => markRead.mutate(eventId) }
}
