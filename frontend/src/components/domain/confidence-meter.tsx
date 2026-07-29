import type { ConfidenceBreakdownDto } from '@/lib/api/types'
import { cn } from '@/lib/cn'

const FACTOR_LABELS: Record<keyof Omit<ConfidenceBreakdownDto, 'overall'>, string> = {
  data_quality: 'Data quality',
  feature_completeness: 'Feature completeness',
  model_certainty: 'Model certainty',
  historical_accuracy: 'Historical accuracy',
  sample_size_adequacy: 'Sample size adequacy',
  market_liquidity: 'Market liquidity',
  temporal_relevance: 'Temporal relevance',
  ensemble_agreement: 'Ensemble agreement',
  calibration_quality: 'Calibration quality',
  volatility_penalty: 'Volatility penalty',
}

export function toneForScore(score: number): 'high' | 'medium' | 'low' {
  if (score >= 0.7) return 'high'
  if (score >= 0.4) return 'medium'
  return 'low'
}

const TONE_BAR_CLASS = {
  high: 'bg-confidence-high',
  medium: 'bg-confidence-medium',
  low: 'bg-confidence-low',
} as const

const TONE_TEXT_CLASS = {
  high: 'text-confidence-high',
  medium: 'text-confidence-medium',
  low: 'text-confidence-low',
} as const

export function ConfidenceMeter({ confidence, className }: { confidence: ConfidenceBreakdownDto; className?: string }) {
  const overallTone = toneForScore(confidence.overall)

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-text-primary">Overall confidence</span>
        <span className={cn('font-mono text-lg font-semibold', TONE_TEXT_CLASS[overallTone])}>
          {Math.round(confidence.overall * 100)}%
        </span>
      </div>
      <div className="flex flex-col gap-2.5">
        {(Object.keys(FACTOR_LABELS) as Array<keyof typeof FACTOR_LABELS>).map((key) => {
          const score = confidence[key]
          const tone = toneForScore(score)
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="w-40 shrink-0 text-xs text-text-secondary">{FACTOR_LABELS[key]}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-secondary">
                <div
                  className={cn('h-full rounded-full transition-[width]', TONE_BAR_CLASS[tone])}
                  style={{ width: `${Math.round(score * 100)}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right font-mono text-xs text-text-muted">
                {Math.round(score * 100)}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
