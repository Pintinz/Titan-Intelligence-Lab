import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { PredictionCard } from '@/components/domain/prediction-card'
import { predictionsApi } from '@/lib/api/predictions'

export function PredictionComparisonPanel({
  open,
  onOpenChange,
  predictionIds,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  predictionIds: string[]
}) {
  const compareQuery = useQuery({
    queryKey: ['predictions', 'compare', predictionIds],
    queryFn: () => predictionsApi.compare(predictionIds),
    enabled: open && predictionIds.length >= 2,
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>Comparing {predictionIds.length} predictions</DialogTitle>
        </DialogHeader>
        <div className="max-h-[70vh] overflow-y-auto">
          {compareQuery.isLoading && (
            <div className="grid gap-4 sm:grid-cols-2">
              {predictionIds.map((id) => (
                <Skeleton key={id} className="h-56" />
              ))}
            </div>
          )}
          {compareQuery.isError && (
            <ErrorState description="Could not load a side-by-side comparison." onRetry={() => compareQuery.refetch()} />
          )}
          {compareQuery.data && (
            <div className="grid gap-4 sm:grid-cols-2">
              {compareQuery.data.map((prediction) => (
                <PredictionCard key={prediction.id} prediction={prediction} />
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
