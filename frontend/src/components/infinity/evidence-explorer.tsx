import { CircleCheck, TriangleAlert, ChevronDown } from 'lucide-react'
import { InfinityLabel } from './primitives/panel'
import { InfinityConfidenceRing } from './charts/confidence-ring'
import { InfinityConfidenceTelemetry } from './confidence-telemetry'
import { InfinityRadarChart } from './charts/radar-chart'
import { InfinityBadge } from './primitives/badge'
import type { PredictionDto } from '@/lib/api/types'

const CONFIDENCE_AXES: Array<[key: string, label: string]> = [
  ['feature_quality', 'Data Quality'],
  ['feature_freshness', 'Freshness'],
  ['historical_accuracy', 'Historical'],
  ['knowledge_graph_completeness', 'Context Coverage'],
  ['news_reliability', 'News'],
  ['community_reliability', 'Community'],
  ['data_completeness', 'Completeness'],
  ['model_reliability', 'AI Reliability'],
  ['prediction_stability', 'Stability'],
]

export function humanizeFactorKey(key: string): string {
  const lastSegment = key.split('.').pop() ?? key
  return lastSegment
    .replace(/_last(\d+)/i, ' (last $1)')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

type RiskLevel = 'Low risk' | 'Moderate risk' | 'High risk'

/** A qualitative read on how much uncertainty this verdict carries — the inverse of overall
 * confidence, banded rather than shown as a raw score. Real (derived from the same composite
 * confidence the ring/telemetry already show), not a separate backend field. */
function riskLevel(composite: number): { label: RiskLevel; tone: string } {
  if (composite >= 0.75) return { label: 'Low risk', tone: 'var(--infinity-success)' }
  if (composite >= 0.5) return { label: 'Moderate risk', tone: 'var(--infinity-warning)' }
  return { label: 'High risk', tone: 'var(--infinity-danger)' }
}

export type TeamRef = { name: string; logoUrl?: string | null }

/** `WeightedOrdinalPredictor` emits the real, final value for every `HOME_DRAW_AWAY` market as
 * one of these three literals directly (`modules/predictions/infrastructure/predictors/
 * weighted_scoring.py`) — correct as backend output, but a generic code rather than something a
 * user should read. The caller already knows which team is home/away for this fixture, so this
 * resolves the verdict to the actual team (crest included) instead of showing the raw label. */
export function resolveVerdict(
  value: unknown,
  homeTeam?: TeamRef,
  awayTeam?: TeamRef
): { text: string; team?: TeamRef } {
  if (value === 'HOME_WIN' && homeTeam) return { text: homeTeam.name, team: homeTeam }
  if (value === 'AWAY_WIN' && awayTeam) return { text: awayTeam.name, team: awayTeam }
  if (value === 'DRAW') return { text: 'Draw' }
  return { text: String(value) }
}

/** Same team/draw resolution `resolveVerdict` applies to the winning `value`, applied to every
 * key in `probability_distribution` so "Alternative Outcomes" reads like the verdict does rather
 * than showing raw backend codes for the outcomes that didn't win. */
export function resolveOutcomeLabel(key: string, homeTeam?: TeamRef, awayTeam?: TeamRef): string {
  if (key === 'HOME_WIN' && homeTeam) return homeTeam.name
  if (key === 'AWAY_WIN' && awayTeam) return awayTeam.name
  if (key === 'DRAW') return 'Draw'
  if (key === 'OTHER') return 'Other scoreline'
  return key
}

/** Ranked, winner-first view of every outcome a classification-shaped market considered — the
 * "Alternative Outcomes" the Universal Probability Engine spec calls for, sourced from
 * `Prediction.probability_distribution` (empty for a regression-shaped market, where
 * `RegressionRange` below renders instead). */
function AlternativeOutcomes({
  distribution,
  winningValue,
  homeTeam,
  awayTeam,
}: {
  distribution: Record<string, number>
  winningValue: unknown
  homeTeam?: TeamRef
  awayTeam?: TeamRef
}) {
  const sorted = Object.entries(distribution ?? {}).sort(([, a], [, b]) => b - a)
  if (sorted.length === 0) return null

  // A ranked Top-N view (Universal Probability Engine spec), not a dump of every possible
  // outcome — a CORRECT_SCORE-shaped market's grid alone has 37 entries. Always keeps the
  // winning outcome visible even on the rare chance it falls outside the top slice.
  const TOP_N = 8
  const entries = sorted.slice(0, TOP_N)
  if (!entries.some(([key]) => key === winningValue)) {
    const winnerEntry = sorted.find(([key]) => key === winningValue)
    if (winnerEntry) entries.splice(TOP_N - 1, 1, winnerEntry)
  }
  const hiddenCount = sorted.length - entries.length

  return (
    <div>
      <InfinityLabel>Alternative outcomes</InfinityLabel>
      <ul className="mt-2 space-y-1.5">
        {entries.map(([key, probability]) => {
          const isWinner = key === winningValue
          return (
            <li key={key} className="flex items-center gap-2">
              <span
                className={`w-28 shrink-0 truncate font-infinity-body text-[12px] sm:w-36 ${isWinner ? 'font-semibold text-infinity-text-primary' : 'text-infinity-text-secondary'}`}
              >
                {resolveOutcomeLabel(key, homeTeam, awayTeam)}
              </span>
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-infinity-ground-2">
                <span
                  className="block h-full rounded-full"
                  style={{
                    width: `${Math.round(probability * 100)}%`,
                    background: isWinner ? 'var(--infinity-domain-predictions)' : 'var(--infinity-text-muted)',
                  }}
                />
              </span>
              <span className="w-10 shrink-0 text-right font-infinity-mono text-[11px] tabular-nums text-infinity-text-secondary">
                {Math.round(probability * 100)}%
              </span>
            </li>
          )
        })}
      </ul>
      {hiddenCount > 0 && (
        <p className="mt-1.5 font-infinity-body text-[11px] text-infinity-text-muted">+{hiddenCount} more outcomes</p>
      )}
    </div>
  )
}

/** The regression-shaped sibling of `AlternativeOutcomes` — a predicted continuous value has no
 * outcome distribution, so this renders `confidence_interval`/`expected_error` instead (Universal
 * Probability Engine spec: "regression markets return Prediction / Confidence Interval / Expected
 * Error / Reliability, not a fake probability"). */
function RegressionRange({
  value,
  confidenceInterval,
  expectedError,
}: {
  value: unknown
  confidenceInterval: [number, number] | null
  expectedError: number | null
}) {
  if (!confidenceInterval && expectedError === null) return null

  return (
    <div>
      <InfinityLabel>Prediction range</InfinityLabel>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <div>
          <dt className="font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">Predicted</dt>
          <dd className="font-infinity-mono text-[13px] tabular-nums text-infinity-text-primary">{String(value)}</dd>
        </div>
        {confidenceInterval && (
          <div>
            <dt className="font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">Confidence interval</dt>
            <dd className="font-infinity-mono text-[13px] tabular-nums text-infinity-text-primary">
              {confidenceInterval[0].toFixed(2)} – {confidenceInterval[1].toFixed(2)}
            </dd>
          </div>
        )}
        {expectedError !== null && (
          <div>
            <dt className="font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">Expected error</dt>
            <dd className="font-infinity-mono text-[13px] tabular-nums text-infinity-text-primary">±{expectedError.toFixed(2)}</dd>
          </div>
        )}
      </dl>
    </div>
  )
}

function VerdictCrest({ team, size }: { team: TeamRef; size: 'lg' | 'sm' }) {
  const dimension = size === 'lg' ? 'size-7' : 'size-5'
  if (team.logoUrl) {
    return <img src={team.logoUrl} alt="" className={`${dimension} shrink-0 rounded-sm object-contain`} loading="lazy" />
  }
  return (
    <span
      aria-hidden="true"
      className={`flex ${dimension} shrink-0 items-center justify-center rounded-sm bg-infinity-ground-2 font-infinity-mono text-[10px] font-semibold text-infinity-text-muted`}
    >
      {team.name.charAt(0).toUpperCase()}
    </span>
  )
}

/**
 * The full "why should I trust this" chain for one AI verdict — verdict, risk, confidence ring +
 * telemetry, a plain-language confidence-drivers checklist, and the model's own narrated
 * reasoning. Previously duplicated near-verbatim between the Match Intelligence page and the
 * Assistant workspace's evidence panel; extracted here so both stay in sync and any future
 * consumer gets it for free.
 *
 * `explanation.knowledge_graph_evidence`/`news_contribution`/`community_contribution` are raw
 * engine output (graph-edge triples keyed by internal ids, e.g. "<uuid> involved_in <uuid>") —
 * never presentable to an end user, so this component never renders them at all (not even folded
 * away in Technical Details) — the same "never expose backend internals" posture as everything
 * else in this file.
 *
 * `variant="full"` is the wider Match Intelligence layout (larger ring, checklist-style drivers,
 * a collapsible Technical Details section for the axis breakdown/radar). `variant="compact"` is
 * the narrower single-column layout used in a sidebar rail (Assistant workspace, Watchlist) —
 * same data, radar shown inline since there's no separate technical-details affordance there.
 */
export function InfinityEvidenceExplorer({
  prediction,
  variant = 'compact',
  homeTeam,
  awayTeam,
}: {
  prediction: PredictionDto
  variant?: 'full' | 'compact'
  /** The fixture's home/away team, when known — resolves a `HOME_WIN`/`AWAY_WIN` verdict to the
   * actual team (crest + name) instead of the raw label. Omit where no fixture is in scope (a
   * team/player prediction, or a caller with no team context yet); the raw value still renders. */
  homeTeam?: TeamRef
  awayTeam?: TeamRef
}) {
  const { confidence, explanation } = prediction
  const axes = CONFIDENCE_AXES.map(([, label]) => label)
  const values = CONFIDENCE_AXES.map(([key]) => confidence[key as keyof typeof confidence])
  const hasEvidence = explanation.top_positive_features.length > 0 || explanation.top_negative_features.length > 0
  const ringSize = variant === 'full' ? 96 : 56
  const radarSize = variant === 'full' ? 200 : 180
  const risk = riskLevel(confidence.composite)
  const verdict = resolveVerdict(prediction.value, homeTeam, awayTeam)

  return (
    <div className="space-y-5">
      {variant === 'full' ? (
        <div className="flex flex-wrap items-center gap-6">
          <InfinityConfidenceRing value={confidence.composite} size={ringSize} />
          <div>
            <InfinityLabel>AI Verdict</InfinityLabel>
            <div className="mt-1 flex items-center gap-2">
              {verdict.team && <VerdictCrest team={verdict.team} size="lg" />}
              <p className="font-infinity-telemetry text-2xl font-semibold text-infinity-text-primary">{verdict.text}</p>
              <InfinityBadge tone={risk.tone}>{risk.label}</InfinityBadge>
            </div>
          </div>
          <div className="min-w-[220px] flex-1">
            <InfinityConfidenceTelemetry probability={prediction.probability} confidence={confidence.composite} />
          </div>
        </div>
      ) : null}

      <AlternativeOutcomes
        distribution={prediction.probability_distribution}
        winningValue={prediction.value}
        homeTeam={homeTeam}
        awayTeam={awayTeam}
      />
      <RegressionRange
        value={prediction.value}
        confidenceInterval={prediction.confidence_interval}
        expectedError={prediction.expected_error}
      />

      {variant !== 'full' && (
        <>
          <div>
            <InfinityLabel>AI Verdict</InfinityLabel>
            <div className="mt-1 flex items-center gap-2">
              {verdict.team && <VerdictCrest team={verdict.team} size="sm" />}
              <p className="font-infinity-telemetry text-lg font-semibold text-infinity-text-primary">{verdict.text}</p>
              <InfinityBadge tone={risk.tone}>{risk.label}</InfinityBadge>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <InfinityConfidenceRing value={confidence.composite} size={ringSize} />
            <InfinityConfidenceTelemetry probability={prediction.probability} confidence={confidence.composite} />
          </div>
          <InfinityRadarChart axes={axes} values={values} size={radarSize} tone="var(--infinity-domain-predictions)" />
        </>
      )}

      {variant === 'full' && explanation.ai_explanation && (
        <p className="font-infinity-body text-[14px] leading-relaxed text-infinity-text-secondary">
          {explanation.ai_explanation}
        </p>
      )}

      {hasEvidence &&
        (variant === 'full' ? (
          <div>
            <InfinityLabel>Confidence drivers</InfinityLabel>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2">
              {explanation.top_positive_features.map(([featureKey, contribution]) => (
                <li key={featureKey} className="flex items-start gap-2">
                  <CircleCheck className="mt-0.5 size-3.5 shrink-0 text-infinity-success" aria-hidden="true" />
                  <span className="font-infinity-body text-[12px] text-infinity-text-secondary">
                    {humanizeFactorKey(featureKey)}{' '}
                    <span className="font-infinity-mono text-infinity-success">+{contribution.toFixed(2)}</span>{' '}
                    favors this verdict
                  </span>
                </li>
              ))}
              {explanation.top_negative_features.map(([featureKey, contribution]) => (
                <li key={featureKey} className="flex items-start gap-2">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-infinity-warning" aria-hidden="true" />
                  <span className="font-infinity-body text-[12px] text-infinity-text-secondary">
                    {humanizeFactorKey(featureKey)}{' '}
                    <span className="font-infinity-mono text-infinity-warning">{contribution.toFixed(2)}</span>{' '}
                    works against this verdict
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <div>
            <InfinityLabel>Evidence</InfinityLabel>
            <div className="mt-2 space-y-3">
              <div>
                <p className="font-infinity-body text-[11px] font-semibold text-infinity-success">Supporting evidence</p>
                <ul className="mt-1.5 space-y-1">
                  {explanation.top_positive_features.map(([featureKey, contribution]) => (
                    <li key={featureKey} className="flex justify-between gap-2 font-infinity-mono text-[11px] text-infinity-text-secondary">
                      <span className="truncate">{humanizeFactorKey(featureKey)}</span>
                      <span className="shrink-0">+{contribution.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="font-infinity-body text-[11px] font-semibold text-infinity-danger">Contradicting evidence</p>
                <ul className="mt-1.5 space-y-1">
                  {explanation.top_negative_features.map(([featureKey, contribution]) => (
                    <li key={featureKey} className="flex justify-between gap-2 font-infinity-mono text-[11px] text-infinity-text-secondary">
                      <span className="truncate">{humanizeFactorKey(featureKey)}</span>
                      <span className="shrink-0">{contribution.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ))}

      {variant === 'compact' && explanation.ai_explanation && (
        <div>
          <InfinityLabel>Why TitanIQ believes this</InfinityLabel>
          <p className="mt-2 font-infinity-body text-[12px] text-infinity-text-secondary">{explanation.ai_explanation}</p>
        </div>
      )}

      {variant === 'full' && (
        <details className="group rounded-infinity-md border border-infinity-border-hairline">
          <summary className="flex cursor-pointer list-none items-center justify-between px-3.5 py-2.5 font-infinity-body text-[12px] font-medium text-infinity-text-secondary marker:content-none">
            Technical details
            <ChevronDown className="size-3.5 shrink-0 text-infinity-text-muted transition-transform group-open:rotate-180" aria-hidden="true" />
          </summary>
          <div className="grid gap-6 border-t border-infinity-border-hairline p-3.5 sm:grid-cols-[auto_1fr] sm:items-center">
            <InfinityRadarChart axes={axes} values={values} size={radarSize} tone="var(--infinity-domain-predictions)" />
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
              {CONFIDENCE_AXES.map(([key, label]) => (
                <div key={key}>
                  <dt className="font-infinity-body text-[10px] uppercase tracking-[0.06em] text-infinity-text-muted">{label}</dt>
                  <dd className="font-infinity-mono text-[13px] tabular-nums text-infinity-text-primary">
                    {Math.round(confidence[key as keyof typeof confidence] * 100)}%
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </details>
      )}
    </div>
  )
}
