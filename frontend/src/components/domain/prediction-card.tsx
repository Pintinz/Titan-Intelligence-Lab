import { CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import type { PredictionDto } from '@/lib/api/types'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { ConfidenceMeter } from '@/components/domain/confidence-meter'
import { FeatureImportanceBars } from '@/components/domain/feature-importance-bar'
import { cn } from '@/lib/cn'

const STATUS_BADGE_VARIANT = {
  pending: 'neutral',
  generated: 'info',
  approved: 'success',
  rejected: 'danger',
  published: 'success',
} as const

export function PredictionCard({
  prediction,
  className,
  selectable,
  selected,
  onToggleSelect,
}: {
  prediction: PredictionDto
  className?: string
  selectable?: boolean
  selected?: boolean
  onToggleSelect?: () => void
}) {
  const { explanation, confidence } = prediction
  const statusVariant = STATUS_BADGE_VARIANT[prediction.status as keyof typeof STATUS_BADGE_VARIANT] ?? 'neutral'

  return (
    <Card className={cn('overflow-hidden', selected && 'ring-2 ring-accent-primary', className)}>
      <CardHeader className="flex-row items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          {selectable && (
            <input
              type="checkbox"
              checked={Boolean(selected)}
              onChange={onToggleSelect}
              aria-label={`Select prediction for ${prediction.subject_ref}`}
              className="mt-1.5 h-4 w-4 rounded border-border-default accent-[var(--color-accent-primary)]"
            />
          )}
          <div>
            <p className="text-xs text-text-muted">{prediction.subject_ref}</p>
            <p className="mt-1 font-mono text-2xl font-semibold text-text-primary">
              {typeof prediction.value === 'number' ? prediction.value.toFixed(2) : prediction.value}
            </p>
            <p className="text-sm text-text-secondary">
              probability <span className="font-mono text-text-primary">{Math.round(prediction.probability * 100)}%</span>
            </p>
          </div>
        </div>
        <Badge variant={statusVariant}>{prediction.status}</Badge>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
          <Badge variant="accent">model {prediction.model_version}</Badge>
          <CalibrationIndicator explanation={explanation} />
          <span className="font-mono text-text-muted">
            confidence {Math.round(confidence.overall * 100)}%
          </span>
        </div>

        <Accordion type="single" collapsible>
          <AccordionItem value="confidence">
            <AccordionTrigger>Confidence breakdown</AccordionTrigger>
            <AccordionContent>
              <ConfidenceMeter confidence={confidence} />
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="explanation">
            <AccordionTrigger>Explanation</AccordionTrigger>
            <AccordionContent className="flex flex-col gap-4">
              <FeatureImportanceBars positive={explanation.top_positive_features} negative={explanation.top_negative_features} />
              {explanation.knowledge_graph_contribution && (
                <ExplanationSnippet label="Knowledge Graph evidence" text={explanation.knowledge_graph_contribution} />
              )}
              {explanation.news_contribution && (
                <ExplanationSnippet label="News contribution" text={explanation.news_contribution} />
              )}
              {explanation.community_contribution && (
                <ExplanationSnippet label="Community contribution" text={explanation.community_contribution} />
              )}
              {explanation.ai_explanation && <ExplanationSnippet label="Narrative" text={explanation.ai_explanation} />}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </CardContent>
    </Card>
  )
}

function CalibrationIndicator({ explanation }: { explanation: PredictionDto['explanation'] }) {
  const hasShap = Boolean(explanation.shap_explanation)
  return (
    <span className="flex items-center gap-1">
      {hasShap ? (
        <CheckCircle2 className="h-3.5 w-3.5 text-success" aria-hidden="true" />
      ) : (
        <HelpCircle className="h-3.5 w-3.5 text-text-muted" aria-hidden="true" />
      )}
      {hasShap ? 'SHAP explained' : 'Heuristic explanation'}
    </span>
  )
}

function ExplanationSnippet({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
      <p className="mt-1 text-sm text-text-secondary">{text}</p>
    </div>
  )
}

export function PredictionRejectedNotice() {
  return (
    <span className="flex items-center gap-1 text-xs text-danger">
      <XCircle className="h-3.5 w-3.5" /> Rejected
    </span>
  )
}
