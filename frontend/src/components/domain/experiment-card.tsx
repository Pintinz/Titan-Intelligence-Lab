import { FlaskConical } from 'lucide-react'
import type { ExperimentDto } from '@/lib/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function ExperimentCard({ experiment }: { experiment: ExperimentDto }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-4 w-4 text-text-muted" aria-hidden="true" />
          <CardTitle className="font-mono">{experiment.id.slice(0, 8)}</CardTitle>
        </div>
        {experiment.decision ? (
          <Badge variant={experiment.decision === 'accepted' ? 'success' : 'danger'}>{experiment.decision}</Badge>
        ) : (
          <Badge variant="neutral">pending</Badge>
        )}
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2 text-xs text-text-secondary">
        {Object.entries(experiment.metrics).map(([key, value]) => (
          <div key={key} className="flex items-center justify-between rounded-md bg-bg-secondary px-2 py-1">
            <span className="text-text-muted">{key}</span>
            <span className="font-mono text-text-primary">{typeof value === 'number' ? value.toFixed(3) : String(value)}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
