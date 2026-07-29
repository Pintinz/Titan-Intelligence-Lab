import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { KeyValueGrid } from '@/components/domain/key-value-grid'
import { mlPlatformApi } from '@/lib/api/ml-platform'

export function ModelEvaluationsDialog({ modelId, modelKey }: { modelId: string; modelKey: string }) {
  const evaluationsQuery = useQuery({
    queryKey: ['ml', 'evaluations', modelId],
    queryFn: () => mlPlatformApi.listEvaluations(modelId),
    enabled: false,
  })

  return (
    <Dialog onOpenChange={(open) => open && void evaluationsQuery.refetch()}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Evaluations
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Evaluation reports — {modelKey}</DialogTitle>
        </DialogHeader>
        <div className="flex max-h-[60vh] flex-col gap-3 overflow-y-auto">
          {evaluationsQuery.isFetching && <Skeleton className="h-24" />}
          {evaluationsQuery.data?.length === 0 && (
            <p className="text-sm text-text-muted">No evaluation reports recorded for this model yet.</p>
          )}
          {evaluationsQuery.data?.map((evaluation) => (
            <div key={evaluation.id} className="rounded-md border border-border-subtle p-3">
              <p className="font-mono text-xs text-text-muted">{new Date(evaluation.evaluated_at).toLocaleString()}</p>
              <KeyValueGrid data={evaluation.metrics} />
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
