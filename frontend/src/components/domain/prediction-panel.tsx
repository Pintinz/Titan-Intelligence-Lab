import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { ContextualReviewPanel } from '@/components/domain/contextual-review-panel'
import { FootballExplanationPanel } from '@/components/domain/football-explanation-panel'
import { Card } from '@/components/ui/card'
import type { ConfidenceBreakdownDto, PredictionDto } from '@/lib/api/types'

function humanizeFactorKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

export function overallConfidence(confidence: ConfidenceBreakdownDto): number {
  return confidence.composite
}

function confidenceFactors(confidence: ConfidenceBreakdownDto): Array<[string, number]> {
  return Object.entries(confidence).filter((entry): entry is [string, number] => entry[0] !== 'composite')
}

type TeamRef = { name: string; logoUrl?: string | null }

/** `WeightedOrdinalPredictor` emits `HOME_WIN`/`DRAW`/`AWAY_WIN` as the real, final value for
 * every `HOME_DRAW_AWAY` market — correct backend output, but a generic code rather than
 * something a user should read. Resolves it to the actual team name when the caller knows the
 * fixture's home/away teams; falls back to the raw value otherwise. */
function resolveVerdict(value: unknown, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  if (value === 'HOME_WIN' && homeTeam) return homeTeam.name
  if (value === 'AWAY_WIN' && awayTeam) return awayTeam.name
  if (value === 'DRAW') return 'Draw'
  return String(value)
}

function resolveOutcomeLabel(key: string, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  if (key === 'HOME_WIN' && homeTeam) return homeTeam.name
  if (key === 'AWAY_WIN' && awayTeam) return awayTeam.name
  if (key === 'DRAW') return 'Draw'
  if (key === 'OTHER') return 'Other scoreline'
  return key
}

/** The full breakdown view for a generated prediction on the Prediction Laboratory page (Match
 * Intelligence uses `InfinityEvidenceExplorer` instead). Never renders
 * `explanation.knowledge_graph_evidence`/`news_contribution`/`community_contribution` — raw
 * engine output (graph-edge triples keyed by internal ids) that was never presentable to an end
 * user, matching `InfinityEvidenceExplorer`'s posture. */
export function PredictionPanel({
  prediction,
  homeTeam,
  awayTeam,
}: {
  prediction: PredictionDto
  homeTeam?: TeamRef
  awayTeam?: TeamRef
}) {
  const { confidence, explanation } = prediction
  const factors = confidenceFactors(confidence)
  const sortedOutcomes = Object.entries(prediction.probability_distribution ?? {}).sort(([, a], [, b]) => b - a)
  const TOP_N = 8
  const outcomeEntries = sortedOutcomes.slice(0, TOP_N)
  if (!outcomeEntries.some(([key]) => key === prediction.value)) {
    const winnerEntry = sortedOutcomes.find(([key]) => key === prediction.value)
    if (winnerEntry) outcomeEntries.splice(TOP_N - 1, 1, winnerEntry)
  }
  const hiddenOutcomeCount = sortedOutcomes.length - outcomeEntries.length
  const hasRegressionRange = prediction.confidence_interval !== null || prediction.expected_error !== null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-md border border-border-default bg-bg-elevated px-4 py-3">
        <div>
          <p className="text-xs text-text-muted">Prediction</p>
          <p className="font-telemetry text-lg font-medium text-text-primary">
            {resolveVerdict(prediction.value, homeTeam, awayTeam)}
          </p>
        </div>
        <ConfidenceTelemetry confidence={overallConfidence(confidence)} />
      </div>

      {outcomeEntries.length > 0 && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Alternative outcomes</p>
          <ul className="mt-3 space-y-1.5">
            {outcomeEntries.map(([key, probability]) => {
              const isWinner = key === prediction.value
              return (
                <li key={key} className="flex items-center gap-2">
                  <span
                    className={`w-28 shrink-0 truncate text-xs sm:w-36 ${isWinner ? 'font-semibold text-text-primary' : 'text-text-secondary'}`}
                  >
                    {resolveOutcomeLabel(key, homeTeam, awayTeam)}
                  </span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-elevated">
                    <span
                      className={`block h-full rounded-full ${isWinner ? 'bg-accent-primary' : 'bg-border-default'}`}
                      style={{ width: `${Math.round(probability * 100)}%` }}
                    />
                  </span>
                  <span className="w-10 shrink-0 text-right font-mono text-[11px] tabular-nums text-text-secondary">
                    {Math.round(probability * 100)}%
                  </span>
                </li>
              )
            })}
          </ul>
          {hiddenOutcomeCount > 0 && (
            <p className="mt-1.5 text-[11px] text-text-muted">+{hiddenOutcomeCount} more outcomes</p>
          )}
        </Card>
      )}

      {hasRegressionRange && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Prediction range</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            <div>
              <dt className="text-[11px] text-text-muted">Predicted</dt>
              <dd className="font-mono text-sm tabular-nums text-text-primary">{prediction.value}</dd>
            </div>
            {prediction.confidence_interval && (
              <div>
                <dt className="text-[11px] text-text-muted">Confidence interval</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">
                  {prediction.confidence_interval[0].toFixed(2)} – {prediction.confidence_interval[1].toFixed(2)}
                </dd>
              </div>
            )}
            {prediction.expected_error !== null && (
              <div>
                <dt className="text-[11px] text-text-muted">Expected error</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">±{prediction.expected_error.toFixed(2)}</dd>
              </div>
            )}
          </dl>
        </Card>
      )}

      {factors.length > 0 && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Confidence factors</p>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-5">
            {factors.map(([key, value]) => (
              <div key={key}>
                <dt className="text-[11px] text-text-muted">{humanizeFactorKey(key)}</dt>
                <dd className="font-mono text-sm tabular-nums text-text-primary">{Math.round(value * 100)}%</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      {(explanation.top_positive_features.length > 0 || explanation.top_negative_features.length > 0) && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Evidence</p>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-success">Supporting</p>
              <ul className="mt-1.5 space-y-1">
                {explanation.top_positive_features.map(([featureKey, contribution]) => (
                  <li key={featureKey} className="flex justify-between gap-2 font-mono text-xs text-text-secondary">
                    <span className="truncate">{featureKey}</span>
                    <span className="shrink-0">+{contribution.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="text-xs font-medium text-danger">Against</p>
              <ul className="mt-1.5 space-y-1">
                {explanation.top_negative_features.map(([featureKey, contribution]) => (
                  <li key={featureKey} className="flex justify-between gap-2 font-mono text-xs text-text-secondary">
                    <span className="truncate">{featureKey}</span>
                    <span className="shrink-0">{contribution.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {explanation.ai_explanation && (
        <Card className="p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">TitanIQ Insights</p>
          <p className="mt-2 text-sm text-text-secondary">{explanation.ai_explanation}</p>
        </Card>
      )}

      <FootballExplanationPanel explanation={prediction.football_explanation} />

      <ContextualReviewPanel review={prediction.contextual_review} />
    </div>
  )
}
