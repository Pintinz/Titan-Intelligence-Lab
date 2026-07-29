import { Cpu } from 'lucide-react'
import type { ModelDto } from '@/lib/api/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

const STATUS_VARIANT = {
  training: 'info',
  candidate: 'neutral',
  champion: 'success',
  challenger: 'accent',
  retired: 'neutral',
  rejected: 'danger',
} as const

export function ModelCard({ model }: { model: ModelDto }) {
  const statusVariant = STATUS_VARIANT[model.status as keyof typeof STATUS_VARIANT] ?? 'neutral'
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Cpu className="h-4 w-4 text-text-muted" aria-hidden="true" />
          <CardTitle>
            {model.model_key} <span className="text-text-muted">v{model.version}</span>
          </CardTitle>
        </div>
        <Badge variant={statusVariant}>{model.status}</Badge>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2 text-xs text-text-secondary">
        <Badge variant="neutral">{model.algorithm}</Badge>
        <Badge variant="neutral">{model.framework}</Badge>
        {model.deployment_mode && <Badge variant="info">{model.deployment_mode}</Badge>}
      </CardContent>
    </Card>
  )
}
