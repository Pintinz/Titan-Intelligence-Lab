import { useQuery, useQueryClient } from '@tanstack/react-query'
import { predictionsApi } from '@/lib/api/predictions'

/** Mobile V1 monetization. Shared everywhere a "Generate Intelligence" action exists (match
 * detail, Prediction Laboratory, Intelligence Workspace) — one query key, so a credit consumed or
 * granted on any one screen is reflected everywhere else without a manual refetch wiring per
 * page. */
export const PREDICTION_ENTITLEMENT_QUERY_KEY = ['predictions', 'entitlement'] as const

export function usePredictionEntitlement() {
  return useQuery({ queryKey: PREDICTION_ENTITLEMENT_QUERY_KEY, queryFn: () => predictionsApi.entitlement() })
}

export function useInvalidatePredictionEntitlement() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: PREDICTION_ENTITLEMENT_QUERY_KEY })
}
