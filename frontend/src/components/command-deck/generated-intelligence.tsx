import { CircleCheck, Lock, TriangleAlert } from 'lucide-react'
import { resolveOutcomeLabel, resolveVerdict, humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDPanel, CDLabel } from './primitives/panel'
import { CDConfidenceGauge } from './primitives/gauge'
import { CDDistributionBar } from './primitives/telemetry'
import { ApiError } from '@/lib/api/client'
import type { PredictionDto } from '@/lib/api/types'

function riskBand(composite: number): { label: string; tone: string } {
  if (composite >= 0.75) return { label: 'Low risk', tone: 'var(--cd-positive)' }
  if (composite >= 0.5) return { label: 'Moderate risk', tone: 'var(--cd-negative)' }
  return { label: 'High risk', tone: 'var(--cd-negative)' }
}

/**
 * GeneratedIntelligencePanel — the page's centerpiece per the approved brief: one instrument
 * reading, not a scattered card grid. Every number on this panel traces to `PredictionDto` —
 * nothing here is computed client-side beyond formatting. The caller (`match-detail-page.tsx`)
 * only mounts this component once "Generate Intelligence" has actually been clicked — it stays
 * entirely out of the page until then, rather than occupying space with an idle placeholder.
 * Three states while mounted: generating, insufficient-history (a real, honest 409 — never
 * hidden as a generic error), and published (the full reading). `!marketName` is a defensive
 * no-op (the caller never mounts this without a selected market), not a real UI state.
 */
export function GeneratedIntelligencePanel({
  marketName,
  prediction,
  isGenerating,
  error,
  homeTeam,
  awayTeam,
}: {
  marketName: string | null
  prediction: PredictionDto | undefined
  isGenerating: boolean
  error: unknown
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  if (!marketName) return null

  if (isGenerating) {
    return (
      <CDPanel accent className="flex min-h-[220px] flex-col items-center justify-center text-center">
        <div className="relative flex size-8 items-center justify-center">
          <span className="absolute inline-flex size-full animate-ping rounded-full opacity-40 motion-reduce:hidden" style={{ backgroundColor: 'var(--cd-accent)' }} aria-hidden="true" />
          <span className="relative inline-flex size-2.5 rounded-full" style={{ backgroundColor: 'var(--cd-accent)' }} aria-hidden="true" />
        </div>
        <p className="mt-3 font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Analyzing {marketName}…
        </p>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          Reading real historical evidence for this fixture.
        </p>
      </CDPanel>
    )
  }

  if (error) {
    const insufficientHistory = error instanceof ApiError && error.status === 409
    return (
      <CDPanel className="flex min-h-[220px] flex-col items-center justify-center text-center">
        <Lock className="size-6" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <p className="mt-3 font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {insufficientHistory ? 'Not enough verified history yet' : 'Something went wrong'}
        </p>
        <p className="mt-1 max-w-sm font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          {insufficientHistory && error instanceof ApiError ? error.detail : 'Try generating this market again.'}
        </p>
      </CDPanel>
    )
  }

  if (!prediction) return null

  const verdict = resolveVerdict(prediction.value, homeTeam, awayTeam)
  const risk = riskBand(prediction.confidence.composite)
  const hasDistribution = Object.keys(prediction.probability_distribution ?? {}).length > 0
  const distributionEntries = Object.entries(prediction.probability_distribution ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)

  return (
    <CDPanel accent>
      <div className="flex items-center justify-between gap-2">
        <CDLabel tone="accent">{marketName}</CDLabel>
        <span
          className="rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]"
          style={{ backgroundColor: 'var(--cd-accent-muted)', color: 'var(--cd-accent)' }}
        >
          {prediction.status}
        </span>
      </div>

      <div className="mt-5 flex flex-col items-center gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          {verdict.team?.logoUrl && <img src={verdict.team.logoUrl} alt="" className="size-9 shrink-0 object-contain" loading="lazy" />}
          <div>
            <p className="font-[var(--cd-font-display)] text-2xl font-semibold sm:text-3xl" style={{ color: 'var(--cd-text-primary)' }}>
              {verdict.text}
            </p>
            <p className="mt-0.5 font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.06em]" style={{ color: risk.tone }}>
              {risk.label}
            </p>
          </div>
        </div>
        <CDConfidenceGauge value={prediction.confidence.composite} label="Confidence" size={104} />
      </div>

      {hasDistribution && (
        <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Alternative outcomes</CDLabel>
          <div className="mt-3 space-y-2">
            {distributionEntries.map(([key, probability]) => (
              <CDDistributionBar
                key={key}
                label={resolveOutcomeLabel(key, homeTeam, awayTeam)}
                probability={probability}
                isTop={key === prediction.value}
              />
            ))}
          </div>
        </div>
      )}

      {!hasDistribution && (prediction.confidence_interval || prediction.expected_error !== null) && (
        <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Prediction range</CDLabel>
          <dl className="mt-3 grid grid-cols-2 gap-4 sm:grid-cols-3">
            {prediction.confidence_interval && (
              <div>
                <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  Confidence interval
                </dt>
                <dd className="font-[var(--cd-font-tabular)] text-[13px] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                  {prediction.confidence_interval[0].toFixed(2)} – {prediction.confidence_interval[1].toFixed(2)}
                </dd>
              </div>
            )}
            {prediction.expected_error !== null && (
              <div>
                <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  Expected error
                </dt>
                <dd className="font-[var(--cd-font-tabular)] text-[13px] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                  ±{prediction.expected_error.toFixed(2)}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {(prediction.explanation.top_positive_features.length > 0 || prediction.explanation.top_negative_features.length > 0) && (
        <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Evidence</CDLabel>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {prediction.explanation.top_positive_features.map(([key, contribution]) => {
              const rawValue = prediction.feature_snapshot?.[key]
              return (
                <li key={key} className="flex items-start gap-2">
                  <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                  <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    {humanizeFactorKey(key)}
                    {typeof rawValue === 'number' && (
                      <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                        {' '}({rawValue.toFixed(2)})
                      </span>
                    )}{' '}
                    <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-positive)' }}>
                      +{contribution.toFixed(2)}
                    </span>
                  </span>
                </li>
              )
            })}
            {prediction.explanation.top_negative_features.map(([key, contribution]) => {
              const rawValue = prediction.feature_snapshot?.[key]
              return (
                <li key={key} className="flex items-start gap-2">
                  <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                  <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    {humanizeFactorKey(key)}
                    {typeof rawValue === 'number' && (
                      <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                        {' '}({rawValue.toFixed(2)})
                      </span>
                    )}{' '}
                    <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-negative)' }}>
                      {contribution.toFixed(2)}
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {prediction.explanation.ai_explanation && (
        <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Why TitanIQ believes this</CDLabel>
          <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            {prediction.explanation.ai_explanation}
          </p>
        </div>
      )}

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
        <span>Model v{prediction.model_version}</span>
        <span>Generated {new Date(prediction.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
      </div>
    </CDPanel>
  )
}
