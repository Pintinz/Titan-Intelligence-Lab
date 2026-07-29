import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { PredictionCard } from '@/components/domain/prediction-card'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Timeline } from '@/components/domain/timeline'
import { predictionsApi } from '@/lib/api/predictions'

export default function PredictionDetailPage() {
  const { predictionId } = useParams<{ predictionId: string }>()

  const predictionQuery = useQuery({
    queryKey: ['predictions', 'detail', predictionId],
    queryFn: () => predictionsApi.get(predictionId!),
    enabled: Boolean(predictionId),
  })

  const historyQuery = useQuery({
    queryKey: ['predictions', 'history', predictionQuery.data?.subject_ref, predictionQuery.data?.market_id],
    queryFn: () => predictionsApi.history(predictionQuery.data!.subject_ref, predictionQuery.data!.market_id),
    enabled: Boolean(predictionQuery.data),
  })

  if (predictionQuery.isLoading) return <PageLoader />
  if (predictionQuery.isError || !predictionQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this prediction." onRetry={() => predictionQuery.refetch()} />
      </div>
    )
  }

  const prediction = predictionQuery.data

  return (
    <div className="flex flex-col gap-6 p-6">
      <Breadcrumbs
        items={[
          { label: 'Dashboard', to: '/app' },
          { label: 'Prediction Center', to: '/app/predictions' },
          { label: prediction.subject_ref },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <PredictionCard prediction={prediction} />

        <Card>
          <CardHeader>
            <CardTitle>History for {prediction.subject_ref}</CardTitle>
          </CardHeader>
          <CardContent>
            {historyQuery.data && historyQuery.data.length > 0 ? (
              <Timeline
                entries={historyQuery.data.map((p) => ({
                  id: p.id,
                  timestamp: p.generated_at,
                  title: `${p.value} · ${Math.round(p.probability * 100)}%`,
                  description: p.status,
                  tone: p.status === 'approved' || p.status === 'published' ? 'success' : 'neutral',
                }))}
              />
            ) : (
              <p className="text-sm text-text-muted">No prior predictions for this subject.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
