import { CircleCheck, Info, Lock, TriangleAlert } from 'lucide-react'
import { resolveOutcomeLabel, resolveVerdict, humanizeFactorKey, humanizeModelAlgorithm, type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDPanel, CDLabel } from './primitives/panel'
import { CDConfidenceGauge } from './primitives/gauge'
import { CDDistributionBar } from './primitives/telemetry'
import { ApiError } from '@/lib/api/client'
import type { ContextualReviewDto, PredictionDto } from '@/lib/api/types'

/** Expected goals displays as a rounded whole number with an "approximately" mark — the real
 * modeled rate (e.g. 1.7) is still available on hover via the `title` attribute, never discarded,
 * just deprioritized visually. The "≈" prefix keeps this from reading as an exact-score claim,
 * which is what the adjacent tooltip already exists to head off. */
export function formatApproximateGoals(value: number): string {
  return `≈${Math.round(value)}`
}

const SCORE_KEY_PATTERN = /^(\d+)-(\d+)$/

/** Intelligence Center §11/§36 — Correct Score gets a dedicated 2D scoreline matrix instead of
 * the flat top-6 "Alternative outcomes" list every other market uses: a 37-entry ranked list
 * (6x6 grid + OTHER, the real shape `FootballGoalsPoissonAdapter`/the multiclass Champion both
 * produce) reads as noise, but the same numbers read instantly as a matrix. Every probability is
 * `prediction.probability_distribution` verbatim — this never computes a scoreline probability,
 * only lays real ones out on two axes. Returns `null` when the distribution isn't score-shaped
 * (every other market keeps using the flat list), so the caller can render this OR the list, not
 * carry score-matrix logic itself. */
export function parseScoreGrid(distribution: Record<string, number>): { homeMax: number; awayMax: number; otherMass: number } | null {
  let homeMax = -1
  let awayMax = -1
  let scoreKeyCount = 0
  let otherMass = 0
  for (const [key, probability] of Object.entries(distribution)) {
    const match = SCORE_KEY_PATTERN.exec(key)
    if (match) {
      scoreKeyCount += 1
      homeMax = Math.max(homeMax, Number(match[1]))
      awayMax = Math.max(awayMax, Number(match[2]))
    } else if (key === 'OTHER') {
      otherMass = probability
    }
  }
  // Requires at least a real 2x2 grid — a lone "2-1" key with no siblings isn't a matrix-shaped
  // market, just a coincidentally score-like label on some other market.
  if (scoreKeyCount < 4 || homeMax < 1 || awayMax < 1) return null
  return { homeMax, awayMax, otherMass }
}

function ScoreDistributionMatrix({
  distribution,
  selectedValue,
  expectedHomeGoals,
  expectedAwayGoals,
}: {
  distribution: Record<string, number>
  selectedValue: string | number
  expectedHomeGoals?: number
  expectedAwayGoals?: number
}) {
  const grid = parseScoreGrid(distribution)
  if (!grid) return null
  const { homeMax, awayMax, otherMass } = grid
  const maxProbability = Math.max(...Object.values(distribution), 0.0001)
  const homeRows = Array.from({ length: homeMax + 1 }, (_, i) => i)
  const awayCols = Array.from({ length: awayMax + 1 }, (_, i) => i)

  return (
    <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <CDLabel>Score distribution</CDLabel>
      <div className="mt-3 overflow-x-auto">
        <table className="border-separate" style={{ borderSpacing: '3px' }}>
          <caption className="sr-only">Modeled probability for each scoreline, home goals by row and away goals by column</caption>
          <thead>
            <tr>
              <th scope="col" className="w-8" aria-hidden="true" />
              {awayCols.map((away) => (
                <th
                  key={away}
                  scope="col"
                  className="px-1 pb-1 text-center font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.04em]"
                  style={{ color: 'var(--cd-text-muted)' }}
                >
                  {away}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {homeRows.map((home) => (
              <tr key={home}>
                <th
                  scope="row"
                  className="pr-1 text-right font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.04em]"
                  style={{ color: 'var(--cd-text-muted)' }}
                >
                  {home}
                </th>
                {awayCols.map((away) => {
                  const key = `${home}-${away}`
                  const probability = distribution[key] ?? 0
                  const isSelected = key === String(selectedValue)
                  const intensity = probability / maxProbability
                  return (
                    <td key={away} className="p-0">
                      <div
                        className="flex size-11 flex-col items-center justify-center rounded-[var(--cd-radius-sm)] sm:size-12"
                        style={{
                          backgroundColor: `color-mix(in srgb, var(--cd-accent) ${Math.round(intensity * 65)}%, var(--cd-surface-2))`,
                          boxShadow: isSelected ? '0 0 0 1.5px var(--cd-accent) inset' : 'none',
                        }}
                        title={`${home}-${away}: ${(probability * 100).toFixed(1)}%`}
                      >
                        <span
                          className="font-[var(--cd-font-tabular)] text-[10.5px] font-semibold tabular-nums"
                          style={{ color: intensity > 0.35 ? 'var(--cd-text-primary)' : 'var(--cd-text-secondary)' }}
                        >
                          {home}-{away}
                        </span>
                        <span
                          className="font-[var(--cd-font-tabular)] text-[9px] tabular-nums"
                          style={{ color: intensity > 0.35 ? 'var(--cd-text-primary)' : 'var(--cd-text-muted)' }}
                        >
                          {(probability * 100).toFixed(1)}%
                        </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 flex items-center gap-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
        <span className="inline-block size-2.5 rounded-full" style={{ backgroundColor: 'var(--cd-accent)', boxShadow: '0 0 0 1.5px var(--cd-accent) inset' }} aria-hidden="true" />
        Selected scoreline
        {otherMass > 0.005 && <span className="ml-2">· {(otherMass * 100).toFixed(1)}% falls outside this grid</span>}
      </p>
      {typeof expectedHomeGoals === 'number' && typeof expectedAwayGoals === 'number' && scorelineDiffersFromExpectedGoals(selectedValue, expectedHomeGoals, expectedAwayGoals) && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[11px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          Expected goals describe the average scoring rate across the distribution — they don't represent an exact score. The
          selected scoreline is the single highest-probability outcome in the modeled grid.
        </p>
      )}
    </div>
  )
}

function scorelineDiffersFromExpectedGoals(selectedValue: string | number, expectedHomeGoals: number, expectedAwayGoals: number): boolean {
  const match = SCORE_KEY_PATTERN.exec(String(selectedValue))
  if (!match) return false
  return Number(match[1]) !== Math.round(expectedHomeGoals) || Number(match[2]) !== Math.round(expectedAwayGoals)
}

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

  const hasDistribution = Object.keys(prediction.probability_distribution ?? {}).length > 0
  // A REGRESSION-shaped prediction (empty probability_distribution, unlike every
  // classification/multiclass market) has `value` as the backend's raw `f"{raw_score:.4f}"`
  // string — a real predicted number (e.g. a total points/runs prediction), not a label
  // `resolveVerdict` knows how to read. Round it to a whole number for display; every other
  // market keeps going through `resolveVerdict` exactly as before.
  const regressionValue = Number(prediction.value)
  const verdict =
    !hasDistribution && Number.isFinite(regressionValue)
      ? { text: Math.round(regressionValue).toString() }
      : resolveVerdict(prediction.value, homeTeam, awayTeam)
  const risk = riskBand(prediction.confidence.composite)
  const isScoreGrid = hasDistribution && parseScoreGrid(prediction.probability_distribution) !== null
  const distributionEntries = Object.entries(prediction.probability_distribution ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)
  const expectedHomeGoals = prediction.feature_snapshot?.['football.fixture.expected_home_goals']
  const expectedAwayGoals = prediction.feature_snapshot?.['football.fixture.expected_away_goals']
  const hasExpectedGoals = typeof expectedHomeGoals === 'number' && typeof expectedAwayGoals === 'number'

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

      {hasExpectedGoals && (
        <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <div className="flex items-center gap-1.5">
            <CDLabel>Expected goals</CDLabel>
            <Info
              className="size-3 cursor-help"
              style={{ color: 'var(--cd-text-muted)' }}
              aria-label="Expected goals represent modeled scoring rates — the average outcome across the full distribution, not an exact-score prediction."
              role="img"
            >
              <title>Expected goals represent modeled scoring rates — the average outcome across the full distribution, not an exact-score prediction.</title>
            </Info>
          </div>
          <dl className="mt-3 grid grid-cols-3 gap-4">
            <div>
              <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                {homeTeam.name}
              </dt>
              <dd
                className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums"
                style={{ color: 'var(--cd-text-primary)' }}
                title={`Modeled rate: ${(expectedHomeGoals as number).toFixed(2)}`}
              >
                {formatApproximateGoals(expectedHomeGoals as number)}
              </dd>
            </div>
            <div>
              <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                {awayTeam.name}
              </dt>
              <dd
                className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums"
                style={{ color: 'var(--cd-text-primary)' }}
                title={`Modeled rate: ${(expectedAwayGoals as number).toFixed(2)}`}
              >
                {formatApproximateGoals(expectedAwayGoals as number)}
              </dd>
            </div>
            <div>
              <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                Total
              </dt>
              <dd
                className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums"
                style={{ color: 'var(--cd-text-primary)' }}
                title={`Modeled rate: ${((expectedHomeGoals as number) + (expectedAwayGoals as number)).toFixed(2)}`}
              >
                {formatApproximateGoals((expectedHomeGoals as number) + (expectedAwayGoals as number))}
              </dd>
            </div>
          </dl>
        </div>
      )}

      {isScoreGrid && (
        <ScoreDistributionMatrix
          distribution={prediction.probability_distribution}
          selectedValue={prediction.value}
          expectedHomeGoals={hasExpectedGoals ? (expectedHomeGoals as number) : undefined}
          expectedAwayGoals={hasExpectedGoals ? (expectedAwayGoals as number) : undefined}
        />
      )}

      {hasDistribution && !isScoreGrid && (
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

      {prediction.football_explanation && <FootballExplanationSection explanation={prediction.football_explanation} />}

      {prediction.contextual_review && <ContextualReviewSection review={prediction.contextual_review} />}

      <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
        <span>{humanizeModelAlgorithm(prediction.model_algorithm) ?? 'Model'} v{prediction.model_version}</span>
        <span>Generated {new Date(prediction.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</span>
      </div>
    </CDPanel>
  )
}

/**
 * Sports-Analyst Explainability, Command Deck styling — real per-instance model attribution
 * (coefficient/SHAP) translated into football-analyst language, narrated by Gemini but never
 * invented or reordered by it (`analysis` is narration of an already-fixed real number). Distinct
 * from "Why TitanIQ believes this" above (`ai_explanation`, the general engine's free-text take):
 * this section's numbers are traceable, ranked attribution values, not prose. Distinct from
 * `ContextualReviewPanel` elsewhere in the app: this explains what the model itself weighed, not
 * whether fresh evidence changes it. Renders nothing when the parent already checked `explanation`
 * is non-null; internally still degrades quietly if the pipeline itself came back unavailable.
 */
function FootballExplanationSection({ explanation }: { explanation: NonNullable<PredictionDto['football_explanation']> }) {
  if (explanation.status !== 'available') {
    return explanation.unavailable_reason ? (
      <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <CDLabel>Why this prediction</CDLabel>
        <p className="mt-2 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          {explanation.unavailable_reason}
        </p>
      </div>
    ) : null
  }

  const modelDrivers = explanation.context.filter((c) => c.role === 'model_driver')

  return (
    <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <div className="flex items-center justify-between gap-2">
        <CDLabel>Why this prediction</CDLabel>
        <span className="font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
          {explanation.attribution_method === 'shap' ? 'SHAP' : explanation.attribution_method === 'linear_coefficient' ? 'Linear coefficient' : 'Heuristic'}
        </span>
      </div>

      {explanation.verdict && (
        <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
          {explanation.verdict}
        </p>
      )}

      {explanation.market_analysis && (
        <p className="mt-2 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          {explanation.market_analysis}
        </p>
      )}

      {explanation.key_reasons.length > 0 && (
        <ul className="mt-4 space-y-3">
          {explanation.key_reasons.map((reason) => (
            <li key={reason.rank} className="flex items-start gap-2">
              {reason.direction === 'supports' ? (
                <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
              ) : (
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
              )}
              <div className="min-w-0">
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {reason.football_concept}
                  {reason.team ? ` — ${reason.team}` : ''}{' '}
                  <span
                    className="font-[var(--cd-font-tabular)] tabular-nums"
                    style={{ color: reason.direction === 'supports' ? 'var(--cd-positive)' : 'var(--cd-negative)' }}
                  >
                    {reason.direction === 'supports' ? '+' : ''}
                    {reason.contribution.toFixed(2)}
                  </span>
                </span>
                {reason.analysis && (
                  <p className="mt-0.5 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
                    {reason.analysis}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {modelDrivers.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          {modelDrivers.map((item, index) => (
            <li key={index} className="flex items-start justify-between gap-2 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
              <span>{item.description}</span>
              <span
                className="shrink-0 font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]"
                style={{ color: 'var(--cd-accent)' }}
              >
                Model driver
              </span>
            </li>
          ))}
        </ul>
      )}

      {explanation.scoreline_reasoning && <ScorelineReasoningSection reasoning={explanation.scoreline_reasoning} />}

      <EvidenceNarrationGroup label="Injuries" items={explanation.injury_evidence} />
      <EvidenceNarrationGroup label="News" items={explanation.news_evidence} />
      <EvidenceNarrationGroup label="Lineups" items={explanation.lineup_evidence} />

      {explanation.context_quality && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[11px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          {explanation.context_quality}
        </p>
      )}

      {explanation.bottom_line && (
        <p
          className="mt-4 border-t pt-3 font-[var(--cd-font-body)] text-[12px] font-medium leading-relaxed"
          style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-accent)' }}
        >
          {explanation.bottom_line}
        </p>
      )}
    </div>
  )
}

/** Correct-Score-only deep reasoning (spec §2/§3/§4) — home/away goal cases plus a real
 * alternative-scoreline comparison, all grounded in the same distribution the Score Distribution
 * Matrix above already renders. Only mounted when the backend actually supplied it (correct_score
 * markets), so every other market's panel is unaffected. */
function ScorelineReasoningSection({ reasoning }: { reasoning: NonNullable<PredictionDto['football_explanation']>['scoreline_reasoning'] }) {
  if (!reasoning) return null
  return (
    <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <CDLabel>Scoreline reasoning</CDLabel>
      {reasoning.home_goal_case && (
        <p className="mt-2 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
          {reasoning.home_goal_case}
        </p>
      )}
      {reasoning.away_goal_case && (
        <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
          {reasoning.away_goal_case}
        </p>
      )}
      {reasoning.alternative_comparison && (
        <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          {reasoning.alternative_comparison}
        </p>
      )}
    </div>
  )
}

/** One real, verified evidence item per row (spec §5/§6/§17) — `analysis` narrates it when
 * Gemini/the mock did; a real item TitanIQ supplied but nobody narrated still renders with just
 * its own summary, never hidden. Renders nothing for a category with zero real items — no empty
 * "Injuries" heading sitting above nothing. */
function EvidenceNarrationGroup({ label, items }: { label: string; items: NonNullable<PredictionDto['football_explanation']>['injury_evidence'] }) {
  if (!items || items.length === 0) return null
  return (
    <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <CDLabel>{label}</CDLabel>
      <ul className="mt-2 space-y-2">
        {items.map((item) => (
          <li key={item.source_id} className="font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            <span>{item.analysis || item.summary}</span>
            {item.published_at && (
              <span className="ml-1.5 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                · {new Date(item.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

const CONTEXTUAL_STATUS_LABEL: Record<ContextualReviewDto['review_status'], string> = {
  SUPPORTED: 'Supported by current evidence',
  WEAKLY_SUPPORTED: 'Weakly supported',
  NEUTRAL: 'No material change',
  CHALLENGED: 'Challenged by current evidence',
  STRONGLY_CHALLENGED: 'Strongly challenged',
  INSUFFICIENT_CONTEXT: 'Contextual analysis unavailable',
}

function humanizeContextKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/**
 * Gemini Prediction Reasoning Engine, Command Deck styling — a second, independent read on the
 * base prediction above (verified pre-cutoff news/injuries/transfers/lineups/coaching-staff vs.
 * what the quantitative model already computed), never a replacement for it. `confidence_score`
 * is explicitly Gemini's confidence in *this contextual assessment*, not an outcome probability
 * — labeled "Assessment confidence" and kept out of the verdict/gauge above so it can't be
 * mistaken for one. Distinct from `FootballExplanationSection` above: that explains what the
 * model itself weighed; this assesses that prediction against fresh, cutoff-filtered evidence.
 * Renders nothing when the parent already checked `contextual_review` is non-null; internally
 * still degrades to `INSUFFICIENT_CONTEXT` messaging if the reasoning engine came back empty.
 */
function ContextualReviewSection({ review }: { review: ContextualReviewDto }) {
  const isInsufficient = review.review_status === 'INSUFFICIENT_CONTEXT'
  const tone =
    review.review_status === 'SUPPORTED' || review.review_status === 'WEAKLY_SUPPORTED'
      ? { fg: 'var(--cd-positive)', bg: 'var(--cd-positive-muted)' }
      : review.review_status === 'CHALLENGED' || review.review_status === 'STRONGLY_CHALLENGED'
        ? { fg: 'var(--cd-negative)', bg: 'var(--cd-negative-muted)' }
        : { fg: 'var(--cd-text-muted)', bg: 'var(--cd-accent-muted)' }
  const baseline = review.statistical_baseline
  const categories = Object.entries(review.contextual_assessment)

  return (
    <div className="mt-6 border-t pt-5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <div className="flex items-center justify-between gap-2">
        <CDLabel>Contextual review</CDLabel>
        <span
          className="rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]"
          style={{ backgroundColor: tone.bg, color: tone.fg }}
        >
          {CONTEXTUAL_STATUS_LABEL[review.review_status]}
        </span>
      </div>

      <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
        {review.overall_assessment}
      </p>

      {isInsufficient ? (
        review.missing_context.length > 0 && (
          <p className="mt-3 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            No verified evidence yet for: {review.missing_context.map(humanizeContextKey).join(', ')}.
          </p>
        )
      ) : (
        <>
          {baseline.applicable && (
            <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <CDLabel>Statistical baseline</CDLabel>
              {baseline.available && baseline.probabilities ? (
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
                  {Object.entries(baseline.probabilities).map(([outcome, probability]) => (
                    <div key={outcome}>
                      <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                        {humanizeContextKey(outcome)}
                      </dt>
                      <dd className="font-[var(--cd-font-tabular)] text-[13px] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                        {Math.round(probability * 100)}%
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
                  {baseline.reason ?? 'No trained baseline available yet.'}
                </p>
              )}
              {baseline.algorithm && (
                <p className="mt-1 font-[var(--cd-font-tabular)] text-[10px]" style={{ color: 'var(--cd-text-muted)' }}>
                  via {humanizeModelAlgorithm(baseline.algorithm)}
                </p>
              )}
            </div>
          )}

          {categories.length > 0 && (
            <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <CDLabel>Current context</CDLabel>
              <ul className="mt-2 space-y-1.5">
                {categories.map(([category, assessment]) => (
                  <li
                    key={category}
                    className="flex items-start justify-between gap-2 font-[var(--cd-font-body)] text-[12px]"
                    style={{ color: 'var(--cd-text-secondary)' }}
                  >
                    <span>{humanizeContextKey(category)}</span>
                    <span
                      className="shrink-0 font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]"
                      style={{
                        color:
                          assessment.impact === 'POSITIVE'
                            ? 'var(--cd-positive)'
                            : assessment.impact === 'NEGATIVE'
                              ? 'var(--cd-negative)'
                              : 'var(--cd-text-muted)',
                      }}
                    >
                      {humanizeContextKey(assessment.impact)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.supporting_factors.length > 0 && (
            <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <span
                className="font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]"
                style={{ color: 'var(--cd-positive)' }}
              >
                Supporting factors
              </span>
              <ul className="mt-2 space-y-1.5">
                {review.supporting_factors.map((factor, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                    <span className="font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
                      {factor.evidence}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.risk_factors.length > 0 && (
            <div className="mt-4 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <span
                className="font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]"
                style={{ color: 'var(--cd-negative)' }}
              >
                Risk factors
              </span>
              <ul className="mt-2 space-y-1.5">
                {review.risk_factors.map((factor, index) => (
                  <li key={index} className="flex items-start gap-2">
                    <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                    <span className="font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
                      {factor.evidence}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {review.missing_context.length > 0 && (
            <p className="mt-3 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
              No verified data yet for: {review.missing_context.map(humanizeContextKey).join(', ')}.
            </p>
          )}
        </>
      )}

      <div className="mt-4 flex items-center justify-between border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <p className="font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
          Assessment confidence: {review.confidence_level.toLowerCase().replace('_', ' ')} ({Math.round(review.confidence_score * 100)}%)
        </p>
        {review.evidence_quality && (
          <p className="font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
            {review.evidence_quality.source_count} source(s)
          </p>
        )}
      </div>
    </div>
  )
}
