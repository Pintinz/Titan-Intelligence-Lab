import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { Card } from '@/components/ui/card'
import type { PredictionDto } from '@/lib/api/types'

const CONFIDENCE_FACTOR_LABELS: Array<[keyof PredictionDto['confidence'], string]> = [
  ['data_quality', 'Data quality'],
  ['feature_completeness', 'Feature completeness'],
  ['model_certainty', 'Model certainty'],
  ['historical_accuracy', 'Historical accuracy'],
  ['sample_size_adequacy', 'Sample size adequacy'],
  ['market_liquidity', 'Market liquidity'],
  ['temporal_relevance', 'Temporal relevance'],
  ['ensemble_agreement', 'Ensemble agreement'],
  ['calibration_quality', 'Calibration quality'],
  ['volatility_penalty', 'Volatility penalty'],
]

/** The one full breakdown view for a generated prediction — used by Match Intelligence and the
 * Prediction Laboratory alike, so a prediction always explains itself the same way everywhere. */
export function PredictionPanel({ prediction }: { prediction: PredictionDto }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-md border border-border-default bg-bg-elevated px-4 py-3">
        <div>
          <p className="text-xs text-text-muted">Prediction</p>
          <p className="font-telemetry text-lg font-medium text-text-primary">{String(prediction.value)}</p>
        </div>
        <ConfidenceTelemetry confidence={prediction.confidence.overall} />
      </div>

      <Card className="p-4">
        <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Confidence factors</p>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
          {CONFIDENCE_FACTOR_LABELS.map(([key, label]) => (
            <div key={key}>
              <dt className="text-[11px] text-text-muted">{label}</dt>
              <dd className="font-mono text-sm tabular-nums text-text-primary">
                {Math.round((prediction.confidence[key] as number) * 100)}%
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      {(prediction.explanation.top_positive_features.length > 0 ||
        prediction.explanation.top_negative_features.length > 0) && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Evidence</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-success">Supporting</p>
              <ul className="mt-1.5 space-y-1">
                {prediction.explanation.top_positive_features.map((f) => (
                  <li key={f.feature_key} className="flex justify-between gap-2 font-mono text-xs text-text-secondary">
                    <span className="truncate">{f.feature_key}</span>
                    <span className="shrink-0">+{f.contribution.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-medium text-danger">Against</p>
              <ul className="mt-1.5 space-y-1">
                {prediction.explanation.top_negative_features.map((f) => (
                  <li key={f.feature_key} className="flex justify-between gap-2 font-mono text-xs text-text-secondary">
                    <span className="truncate">{f.feature_key}</span>
                    <span className="shrink-0">{f.contribution.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {prediction.explanation.ai_explanation && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">TitanIQ Insights</p>
          <p className="mt-2 text-sm text-text-secondary">{prediction.explanation.ai_explanation}</p>
        </Card>
      )}
    </div>
  )
}
