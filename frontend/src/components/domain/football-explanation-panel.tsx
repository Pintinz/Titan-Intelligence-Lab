import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import type { FootballExplanationDto } from '@/lib/api/types'

const STATUS_TONE: Record<FootballExplanationDto['status'], { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  available: { label: 'Attribution available', variant: 'success' },
  unavailable: { label: 'Explanation unavailable', variant: 'neutral' },
  validation_failed: { label: 'Narration unavailable', variant: 'warning' },
}

const ATTRIBUTION_LABEL: Record<FootballExplanationDto['attribution_method'], string> = {
  linear_coefficient: 'Linear coefficient',
  shap: 'SHAP',
  heuristic_importance: 'Heuristic importance',
  unavailable: 'Unavailable',
}

const ROLE_TONE: Record<FootballExplanationDto['context'][number]['role'], { label: string; className: string }> = {
  model_driver: { label: 'Model driver', className: 'text-accent-primary' },
  supporting_context: { label: 'Supporting context', className: 'text-text-secondary' },
  context_only: { label: 'Context only', className: 'text-text-muted' },
}

/**
 * Sports-Analyst Explainability — real per-instance model attribution (coefficient/SHAP), each
 * reason translated into football-analyst language and narrated (never invented, ranked, or
 * reversed) by Gemini. Distinct from `ContextualReviewPanel`: this answers "why did the model
 * predict this" from the model's own weights; the contextual review answers "does fresh evidence
 * change that prediction." `analysis` text within each reason is narration of an already-fixed,
 * real number — Gemini never supplies `feature`/`contribution`/`direction`/`team` itself, so it
 * cannot overwrite or reverse an attribution. Renders nothing when `explanation` is `null` (flag
 * omitted, or the pipeline degraded silently per its own rule that this must never break the base
 * prediction response).
 */
export function FootballExplanationPanel({ explanation }: { explanation: FootballExplanationDto | null }) {
  if (!explanation) return null

  const tone = STATUS_TONE[explanation.status]
  const isUnavailable = explanation.status !== 'available'
  const modelDrivers = explanation.context.filter((c) => c.role === 'model_driver')
  const otherContext = explanation.context.filter((c) => c.role !== 'model_driver')

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Why this prediction</p>
        <Badge variant={tone.variant}>{tone.label}</Badge>
      </div>

      {isUnavailable ? (
        explanation.unavailable_reason && (
          <p className="mt-3 text-xs text-text-muted">{explanation.unavailable_reason}</p>
        )
      ) : (
        <>
          {explanation.verdict && <p className="mt-2 text-sm text-text-secondary">{explanation.verdict}</p>}

          {explanation.key_reasons.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Key reasons</p>
              <ul className="mt-2 space-y-3">
                {explanation.key_reasons.map((reason) => (
                  <li key={reason.rank} className="text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-1.5">
                        <span className="flex size-4 shrink-0 items-center justify-center rounded-full bg-bg-elevated font-mono text-[10px] text-text-muted">
                          {reason.rank}
                        </span>
                        <span className="font-medium text-text-primary">
                          {reason.football_concept}
                          {reason.team ? ` — ${reason.team}` : ''}
                        </span>
                      </span>
                      <span className={`shrink-0 font-mono tabular-nums ${reason.direction === 'supports' ? 'text-success' : 'text-danger'}`}>
                        {reason.direction === 'supports' ? '+' : ''}
                        {reason.contribution.toFixed(2)}
                      </span>
                    </div>
                    {reason.analysis && <p className="mt-1 pl-5.5 text-text-secondary">{reason.analysis}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {explanation.counter_signals.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Counter signals</p>
              <ul className="mt-2 space-y-2">
                {explanation.counter_signals.map((signal, index) => (
                  <li key={index} className="text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <span className="font-medium text-text-primary">{signal.football_concept}</span>
                      <span className="shrink-0 font-mono tabular-nums text-danger">{signal.contribution.toFixed(2)}</span>
                    </div>
                    {signal.analysis && <p className="mt-1 text-text-secondary">{signal.analysis}</p>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {modelDrivers.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Live context weighed by the model</p>
              <ul className="mt-2 space-y-1.5">
                {modelDrivers.map((item, index) => (
                  <li key={index} className="flex items-start justify-between gap-2 text-xs">
                    <span className="text-text-secondary">{item.description}</span>
                    <span className={`shrink-0 font-medium ${ROLE_TONE[item.role].className}`}>{ROLE_TONE[item.role].label}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {otherContext.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Background context</p>
              <ul className="mt-2 space-y-1.5">
                {otherContext.map((item, index) => (
                  <li key={index} className="flex items-start justify-between gap-2 text-xs">
                    <span className="text-text-secondary">{item.description}</span>
                    <span className={`shrink-0 font-medium ${ROLE_TONE[item.role].className}`}>{ROLE_TONE[item.role].label}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {explanation.match_profile && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Match profile</p>
              <p className="mt-1.5 text-xs text-text-secondary">{explanation.match_profile}</p>
            </div>
          )}

          {explanation.confidence_explanation && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Confidence explanation</p>
              <p className="mt-1.5 text-xs text-text-secondary">{explanation.confidence_explanation}</p>
            </div>
          )}

          {explanation.bottom_line && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium text-accent-primary">Bottom line</p>
              <p className="mt-1.5 text-xs text-text-secondary">{explanation.bottom_line}</p>
            </div>
          )}
        </>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3">
        <p className="text-[10px] text-text-muted">Attribution: {ATTRIBUTION_LABEL[explanation.attribution_method]}</p>
      </div>
    </Card>
  )
}
