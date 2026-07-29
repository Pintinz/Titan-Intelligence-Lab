import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ShieldCheck } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { useAuthStore } from '@/stores/auth-store'
import { isAtLeast } from '@/lib/api/types'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { KeyValueGrid } from '@/components/domain/key-value-grid'

const PIPELINE = [
  { title: 'Prediction Validation', detail: 'Every settled market is compared against the official result.' },
  { title: 'Model Evaluation', detail: 'Champion and challenger models are scored on the same outcome.' },
  { title: 'Learning Report', detail: 'Error signal is attributed back to specific features and markets.' },
  { title: 'Knowledge Graph Update', detail: 'New relationships and context are written back into the graph.' },
  { title: 'Confidence Recalibration', detail: 'Probability calibration is re-fit against the latest outcomes.' },
  { title: 'Retraining Queue', detail: 'Markets crossing a drift threshold are queued for retraining.' },
]

export default function LearningIntelligencePage() {
  const role = useAuthStore((s) => s.profile?.role)
  const isAdmin = !!role && isAtLeast(role, 'administrator')

  const summaryQuery = useQuery({
    queryKey: ['predictions', 'monitoring-summary'],
    queryFn: () => predictionsApi.monitoringSummary(),
  })

  return (
    <div className="mx-auto max-w-4xl space-y-10 p-4 lg:p-8">
      <div>
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Learning Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">
          TitanIQ gets smarter after every match
        </h1>
        <p className="mt-2 text-sm text-text-secondary">
          This is the real pipeline that runs after every settled result — not a marketing diagram.
        </p>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch lg:gap-2">
        {PIPELINE.map((step, i) => (
          <div key={step.title} className="flex items-center gap-2 lg:flex-1 lg:flex-col lg:items-stretch lg:gap-0">
            <Card className="flex-1 p-4">
              <p className="font-telemetry text-xs text-text-muted">Step {i + 1}</p>
              <p className="mt-1 font-display text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1.5 text-xs text-text-secondary">{step.detail}</p>
            </Card>
            {i < PIPELINE.length - 1 && (
              <ArrowRight className="size-4 shrink-0 text-text-muted lg:mx-auto lg:my-2 lg:rotate-90" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>

      <div>
        <p className="mb-3 text-sm font-medium text-text-primary">Prediction monitoring</p>
        <Card className="p-5">
          {summaryQuery.isPending && <Skeleton className="h-20" />}
          {summaryQuery.isError && <ErrorState error={summaryQuery.error} onRetry={() => void summaryQuery.refetch()} />}
          {summaryQuery.data && <KeyValueGrid data={summaryQuery.data} />}
        </Card>
      </div>

      <Card className="flex items-start gap-3 p-4">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent-primary" aria-hidden="true" />
        {isAdmin ? (
          <p className="text-sm text-text-secondary">
            Feature drift, model retraining, and calibration telemetry live in the{' '}
            <Link to="/app/ops" className="text-accent-primary hover:text-accent-primary-hover">
              Operations Center
            </Link>
            .
          </p>
        ) : (
          <p className="text-sm text-text-secondary">
            Feature drift, model retraining, and calibration telemetry are restricted to
            administrator accounts — this page shows everything available at your access level.
          </p>
        )}
      </Card>
    </div>
  )
}
