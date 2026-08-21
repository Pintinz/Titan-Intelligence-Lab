import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import type { ContextualReviewDto } from '@/lib/api/types'

function humanizeKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const STATUS_TONE: Record<ContextualReviewDto['review_status'], { label: string; variant: 'success' | 'warning' | 'danger' | 'neutral' }> = {
  SUPPORTED: { label: 'Supported by current evidence', variant: 'success' },
  WEAKLY_SUPPORTED: { label: 'Weakly supported', variant: 'success' },
  NEUTRAL: { label: 'No material change', variant: 'neutral' },
  CHALLENGED: { label: 'Challenged by current evidence', variant: 'warning' },
  STRONGLY_CHALLENGED: { label: 'Strongly challenged', variant: 'danger' },
  INSUFFICIENT_CONTEXT: { label: 'Contextual analysis unavailable', variant: 'neutral' },
}

const IMPACT_COLOR: Record<string, string> = {
  POSITIVE: 'text-success',
  NEGATIVE: 'text-danger',
  MIXED: 'text-warning',
  NEUTRAL: 'text-text-secondary',
  UNKNOWN: 'text-text-muted',
}

/**
 * The Gemini Prediction Reasoning Engine's structured assessment — a second, independent read on
 * the base prediction above (verified pre-cutoff news/injuries/transfers/lineups vs. what the
 * quantitative model already computed), never a replacement for it. `confidence_score` here is
 * explicitly Gemini's confidence in *this contextual assessment*, not an outcome probability —
 * it is deliberately never placed next to `PredictionPanel`'s own probability/confidence gauge,
 * and always labeled "Assessment confidence" so it can't be mistaken for one. Renders nothing
 * when `review` is `null` (flag omitted, or the engine degraded silently per its own absolute
 * rule that a Gemini failure must never surface as a page error).
 */
export function ContextualReviewPanel({ review }: { review: ContextualReviewDto | null }) {
  if (!review) return null

  const tone = STATUS_TONE[review.review_status]
  const isInsufficient = review.review_status === 'INSUFFICIENT_CONTEXT'
  const baseline = review.statistical_baseline
  const categories = Object.entries(review.contextual_assessment)

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Contextual review</p>
        <Badge variant={tone.variant}>{tone.label}</Badge>
      </div>

      <p className="mt-2 text-sm text-text-secondary">{review.overall_assessment}</p>

      {isInsufficient ? (
        review.missing_context.length > 0 && (
          <p className="mt-3 text-xs text-text-muted">
            No verified evidence yet for: {review.missing_context.map(humanizeKey).join(', ')}.
          </p>
        )
      ) : (
        <>
          {baseline.applicable && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Statistical baseline</p>
              {baseline.available && baseline.probabilities ? (
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
                  {Object.entries(baseline.probabilities).map(([outcome, probability]) => (
                    <div key={outcome}>
                      <dt className="text-[11px] text-text-muted">{humanizeKey(outcome)}</dt>
                      <dd className="font-mono text-sm tabular-nums text-text-primary">{Math.round(probability * 100)}%</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-1 text-xs text-text-muted">{baseline.reason ?? 'No trained baseline available yet.'}</p>
              )}
              {baseline.algorithm && <p className="mt-1 text-[10px] text-text-muted">via {baseline.algorithm}</p>}
            </div>
          )}

          {categories.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Current context</p>
              <ul className="mt-2 space-y-1.5">
                {categories.map(([category, assessment]) => (
                  <li key={category} className="flex items-start justify-between gap-2 text-xs">
                    <span className="text-text-secondary">{humanizeKey(category)}</span>
                    <span className={`shrink-0 font-medium ${IMPACT_COLOR[assessment.impact]}`}>
                      {humanizeKey(assessment.impact)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.supporting_factors.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium text-success">Supporting factors</p>
              <ul className="mt-1.5 space-y-1">
                {review.supporting_factors.map((factor, index) => (
                  <li key={index} className="text-xs text-text-secondary">
                    {factor.evidence}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.risk_factors.length > 0 && (
            <div className="mt-4 border-t border-border-default pt-3">
              <p className="text-[11px] font-medium text-danger">Risk factors</p>
              <ul className="mt-1.5 space-y-1">
                {review.risk_factors.map((factor, index) => (
                  <li key={index} className="text-xs text-text-secondary">
                    {factor.evidence}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.missing_context.length > 0 && (
            <p className="mt-3 text-[11px] text-text-muted">
              No verified data yet for: {review.missing_context.map(humanizeKey).join(', ')}.
            </p>
          )}
        </>
      )}

      <div className="mt-4 flex items-center justify-between border-t border-border-default pt-3">
        <p className="text-[10px] text-text-muted">
          Assessment confidence: {review.confidence_level.toLowerCase().replace('_', ' ')} ({Math.round(review.confidence_score * 100)}%)
        </p>
        {review.evidence_quality && (
          <p className="text-[10px] text-text-muted">{review.evidence_quality.source_count} source(s)</p>
        )}
      </div>
    </Card>
  )
}
