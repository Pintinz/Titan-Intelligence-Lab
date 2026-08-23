import { CircleCheck, TriangleAlert, Clock, Lock } from 'lucide-react'
import { resolveOutcomeLabel, humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDPanel, CDLabel } from './primitives/panel'
import { CDConfidenceGauge } from './primitives/gauge'
import { CDDistributionBar } from './primitives/telemetry'
import { PredictionFreshness } from './prediction-format'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import type { FixtureSummaryDto, MarketReviewDto } from '@/lib/api/types'

/**
 * ActualVsPredictedCard — the one reusable "what TitanIQ predicted vs what actually happened"
 * instrument, extracted from `match-review-page.tsx`'s original `MarketReviewCard` (which now
 * imports this instead of keeping its own copy) and generalized with the pre-completion states
 * Team/Competition Intelligence need when a fixture hasn't finished yet. Every field traces to a
 * real `MarketReviewDto` (`predictionsApi.review()`) — never a second prediction-evaluation
 * mechanism, never a client-side accuracy calculation.
 *
 * State is derived, not passed in — a caller hands over the real fixture and whatever
 * `MarketReviewDto` it has (or doesn't), and this renders the honest state that data implies:
 * upcoming / live / completed-with-comparison / result-pending (completed but no score synced
 * yet) / no-prediction (fixture status doesn't block a comparison, but TitanIQ never generated one).
 */
export function ActualVsPredictedCard({
  fixture,
  market,
  homeTeam,
  awayTeam,
}: {
  fixture: FixtureSummaryDto
  market: MarketReviewDto | undefined
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  const status = fixtureCardStatus(fixture.status)
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const hasActualScore = homeScore !== undefined && awayScore !== undefined

  if (!market) {
    return (
      <CDPanel>
        <CDLabel>Actual vs Predicted</CDLabel>
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
          No prediction available
        </p>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          TitanIQ hasn't generated a prediction for this fixture.
        </p>
      </CDPanel>
    )
  }

  if (status === 'live') {
    return (
      <CDPanel accent>
        <div className="flex items-center gap-1.5">
          <span className="relative flex size-2" aria-hidden="true">
            <span className="absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:hidden" style={{ backgroundColor: 'var(--cd-negative)' }} />
            <span className="relative inline-flex size-2 rounded-full" style={{ backgroundColor: 'var(--cd-negative)' }} />
          </span>
          <CDLabel tone="accent">Live</CDLabel>
        </div>
        <p className="mt-3 font-[var(--cd-font-display)] text-[18px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {homeTeam.name} {hasActualScore ? homeScore : '–'} – {hasActualScore ? awayScore : '–'} {awayTeam.name}
        </p>
        <p className="mt-2 flex items-center gap-1.5 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          <Lock className="size-3.5 shrink-0" aria-hidden="true" />
          Prediction locked before kickoff — {market.market_name}: {resolveOutcomeLabel(market.predicted_value, homeTeam, awayTeam)} (
          {(market.probability * 100).toFixed(1)}%). Final evaluation pending.
        </p>
      </CDPanel>
    )
  }

  if (status === 'upcoming') {
    return (
      <CDPanel>
        <CDLabel>Prediction</CDLabel>
        <div className="mt-3 flex items-center justify-between gap-3">
          <div>
            <p className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              {market.market_name}
            </p>
            <p className="mt-0.5 font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
              {resolveOutcomeLabel(market.predicted_value, homeTeam, awayTeam)}
              <span className="ml-2 font-[var(--cd-font-tabular)] text-[13px] font-normal tabular-nums" style={{ color: 'var(--cd-accent)' }}>
                {(market.probability * 100).toFixed(1)}%
              </span>
            </p>
          </div>
          <CDConfidenceGauge value={market.confidence} size={56} />
        </div>
        <p className="mt-3 flex items-center gap-1.5 border-t pt-3 font-[var(--cd-font-body)] text-[12px]" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
          <Clock className="size-3.5 shrink-0" aria-hidden="true" />
          Match has not been completed.
        </p>
        <div className="mt-1.5">
          <PredictionFreshness generatedAt={market.generated_at} />
        </div>
      </CDPanel>
    )
  }

  // status === 'completed' from here — a real score must still exist to compare against.
  if (!hasActualScore) {
    return (
      <CDPanel>
        <CDLabel>Actual vs Predicted</CDLabel>
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
          Final result pending
        </p>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          TitanIQ marked this fixture as completed but hasn't received a verified final score yet.
        </p>
      </CDPanel>
    )
  }

  const resolved = market.is_correct !== null
  const distributionEntries = Object.entries(market.probability_distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)

  return (
    <CDPanel accent={resolved && market.is_correct === true}>
      <div className="flex items-center justify-between gap-2">
        <CDLabel tone="accent">Actual vs Predicted</CDLabel>
        {resolved ? (
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.05em]"
            style={{
              color: market.is_correct ? 'var(--cd-positive)' : 'var(--cd-negative)',
              backgroundColor: market.is_correct ? 'var(--cd-positive-muted)' : 'var(--cd-negative-muted)',
            }}
          >
            {market.is_correct ? <CircleCheck className="size-3" aria-hidden="true" /> : <TriangleAlert className="size-3" aria-hidden="true" />}
            {market.is_correct ? 'Correct' : 'Missed'}
          </span>
        ) : (
          <span className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
            Awaiting resolution
          </span>
        )}
      </div>

      <p className="mt-3 font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
        {homeTeam.name} {homeScore} – {awayScore} {awayTeam.name}
      </p>

      <div className="mt-4 flex items-center justify-between gap-4">
        <div>
          <p className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            {market.market_name} — TitanIQ predicted
          </p>
          <p className="mt-0.5 font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            {resolveOutcomeLabel(market.predicted_value, homeTeam, awayTeam)}
          </p>
          {resolved && (
            <>
              <p className="mt-2 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                Actually happened
              </p>
              <p className="mt-0.5 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                {resolveOutcomeLabel(market.actual_value!, homeTeam, awayTeam)}
              </p>
            </>
          )}
        </div>
        <CDConfidenceGauge value={market.confidence} size={84} label="Confidence" />
      </div>

      <p className="mt-3 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
        Probability: {(market.probability * 100).toFixed(1)}%
      </p>
      <div className="mt-1.5">
        <PredictionFreshness generatedAt={market.generated_at} />
      </div>

      {distributionEntries.length > 0 && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Probability distribution</CDLabel>
          <div className="mt-3 space-y-2">
            {distributionEntries.map(([key, probability]) => (
              <CDDistributionBar key={key} label={resolveOutcomeLabel(key, homeTeam, awayTeam)} probability={probability} isTop={key === market.predicted_value} />
            ))}
          </div>
        </div>
      )}

      {(market.top_positive_features.length > 0 || market.top_negative_features.length > 0) && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Evidence TitanIQ used</CDLabel>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {market.top_positive_features.map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-positive)' }}>
                    +{contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
            {market.top_negative_features.map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-negative)' }}>
                    {contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {market.ai_explanation && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>{resolved ? (market.is_correct ? 'Why TitanIQ was right' : 'Why TitanIQ was wrong') : 'Why TitanIQ believes this'}</CDLabel>
          <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            {market.ai_explanation}
          </p>
        </div>
      )}
    </CDPanel>
  )
}
