import type { ReactNode } from 'react'
import { useQuery, useQueries } from '@tanstack/react-query'
import { Sparkles, TrendingUp } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { CDPanel, CDLabel } from './primitives/panel'
import { GeneratedIntelligencePanel } from './generated-intelligence'
import { ActualVsPredictedCard } from './actual-vs-predicted-card'
import { latestByMarket } from './workspace/workspace-tabs'
import { MATCH_WINNER_SUFFIX, CORRECT_SCORE_SUFFIX, timeAgo, PredictionFreshness } from './prediction-format'
import { resolveOutcomeLabel, type TeamRef } from '@/components/infinity/evidence-explorer'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import type { FixtureSummaryDto, PredictionMarketDto } from '@/lib/api/types'

// Re-exported so every existing external import of these (Competition Intelligence, tests) keeps
// working unchanged — the real definitions now live in `prediction-format.tsx` to break a
// circular import with `actual-vs-predicted-card.tsx` (which also needs `PredictionFreshness`).
export { MATCH_WINNER_SUFFIX, CORRECT_SCORE_SUFFIX, timeAgo, PredictionFreshness }

/** Bounds the history fan-out (one `review()` call per recent completed fixture) to a small,
 * fixed page — real aggregation, never an unbounded per-entity request volume. */
const HISTORY_FIXTURE_CAP = 10

/**
 * PREDICTION INTELLIGENCE — the one section of the Team Detail page connecting the team's next
 * relevant fixture to TitanIQ's already-generated prediction(s) for it. Deliberately thin: every
 * probability/confidence/explanation/evidence value renders through the existing
 * `GeneratedIntelligencePanel` (Match Intelligence's own centerpiece) rather than a second,
 * parallel rendering of the same `PredictionDto` fields — this component's only real job is
 * locating the right predictions and laying out the cross-market summary that doesn't exist
 * anywhere else yet.
 */
export function PredictionIntelligenceSection({
  nextFixture,
  markets,
  marketsLoading,
  recentCompletedFixtures,
}: {
  nextFixture: FixtureSummaryDto | undefined
  markets: PredictionMarketDto[]
  marketsLoading: boolean
  recentCompletedFixtures: FixtureSummaryDto[]
}) {
  const mostRecentCompleted = recentCompletedFixtures[0]

  return (
    <div className="command-deck space-y-4">
      {mostRecentCompleted && <RecentResultComparison fixture={mostRecentCompleted} />}
      {nextFixture ? (
        <NextMatchPrediction nextFixture={nextFixture} markets={markets} marketsLoading={marketsLoading} />
      ) : (
        <InfinityEmptyState
          icon={Sparkles}
          title="No upcoming prediction"
          description="Prediction Intelligence will appear when TitanIQ has a forecast for the team's next monitored fixture."
        />
      )}
      <PredictionHistoryPanel fixtures={recentCompletedFixtures} />
    </div>
  )
}

/** Phase 10 (post-match resolution pipeline, 2026-08-23) — "Fixture → Prediction Intelligence →
 * Actual vs Predicted" for a team's most recent completed fixture. Renders nothing while loading
 * or when TitanIQ never generated a prediction for it (an honest, common case — `market` stays
 * `undefined` and `ActualVsPredictedCard` itself renders "No prediction available"). */
function RecentResultComparison({ fixture }: { fixture: FixtureSummaryDto }) {
  const reviewQuery = useQuery({
    queryKey: ['predictions', 'review', fixture.id],
    queryFn: () => predictionsApi.review(fixture.id),
  })
  if (reviewQuery.isPending) return <InfinitySkeleton className="h-24" />
  const primaryMarket =
    reviewQuery.data?.markets.find((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX)) ?? reviewQuery.data?.markets[0]
  if (!primaryMarket) return null
  return (
    <ActualVsPredictedCard
      fixture={fixture}
      market={primaryMarket}
      homeTeam={{ name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }}
      awayTeam={{ name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }}
    />
  )
}

function NextMatchPrediction({
  nextFixture,
  markets,
  marketsLoading,
}: {
  nextFixture: FixtureSummaryDto
  markets: PredictionMarketDto[]
  marketsLoading: boolean
}) {
  const homeTeam: TeamRef = { name: nextFixture.home_team.name, logoUrl: nextFixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: nextFixture.away_team.name, logoUrl: nextFixture.away_team.logo_url }
  const historyQuery = useQuery({
    queryKey: ['predictions', 'history', nextFixture.id],
    queryFn: () => predictionsApi.history(nextFixture.id),
  })

  if (marketsLoading || historyQuery.isPending) {
    return (
      <div className="space-y-3">
        <InfinitySkeleton className="h-6 w-64" />
        <InfinitySkeleton className="h-56" />
      </div>
    )
  }

  if (historyQuery.isError) {
    return (
      <CDPanel>
        <p className="font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Prediction Intelligence unavailable
        </p>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          Unable to retrieve the latest prediction for this fixture.
        </p>
      </CDPanel>
    )
  }

  if (markets.length === 0) {
    return (
      <InfinityEmptyState icon={Sparkles} title="Coverage building" description="TitanIQ has not yet trained a production market for this sport." />
    )
  }

  const latest = latestByMarket(historyQuery.data ?? [])
  const generatedMarkets = markets.filter((m) => latest.has(m.id))

  if (generatedMarkets.length === 0) {
    return (
      <InfinityEmptyState
        icon={Sparkles}
        title="Prediction not available yet"
        description="TitanIQ has not generated a prediction for this fixture."
      />
    )
  }

  const primaryMarket = generatedMarkets.find((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX)) ?? generatedMarkets[0]
  const primaryPredictionId = latest.get(primaryMarket.id)!.id
  const hasMatchWinner = generatedMarkets.some((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX))
  const hasCorrectScore = generatedMarkets.some((m) => m.market_key.endsWith(CORRECT_SCORE_SUFFIX))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
          {homeTeam.name} vs {awayTeam.name} · {nextFixture.competition_name} ·{' '}
          {new Date(nextFixture.scheduled_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
        </p>
        <PredictionFreshness generatedAt={latest.get(primaryMarket.id)!.generated_at} />
      </div>

      <PrimaryMarketPanel marketName={primaryMarket.name} predictionId={primaryPredictionId} homeTeam={homeTeam} awayTeam={awayTeam} />

      {generatedMarkets.length > 1 && (
        <MarketIntelligenceTable markets={generatedMarkets} latest={latest} homeTeam={homeTeam} awayTeam={awayTeam} />
      )}

      {hasMatchWinner && hasCorrectScore && <CrossMarketInterpretation markets={generatedMarkets} latest={latest} homeTeam={homeTeam} awayTeam={awayTeam} />}
    </div>
  )
}

function PrimaryMarketPanel({
  marketName,
  predictionId,
  homeTeam,
  awayTeam,
}: {
  marketName: string
  predictionId: string
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  const detailQuery = useQuery({
    queryKey: ['predictions', predictionId],
    queryFn: () => predictionsApi.get(predictionId),
  })
  return (
    <GeneratedIntelligencePanel
      marketName={marketName}
      prediction={detailQuery.data}
      isGenerating={detailQuery.isPending}
      error={detailQuery.error}
      homeTeam={homeTeam}
      awayTeam={awayTeam}
    />
  )
}

/** Every market TitanIQ has already generated for this fixture, compactly — the "Market
 * Intelligence" table (spec §15). Values come straight from `history()`'s own
 * `PredictionSummaryDto` rows (already fetched above), no per-market extra request. */
function MarketIntelligenceTable({
  markets,
  latest,
  homeTeam,
  awayTeam,
}: {
  markets: PredictionMarketDto[]
  latest: ReturnType<typeof latestByMarket>
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  return (
    <CDPanel padding="tight">
      <CDLabel>Market intelligence</CDLabel>
      <ul className="mt-3 divide-y" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {markets.map((market) => {
          const prediction = latest.get(market.id)!
          return (
            <li key={market.id} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
              <span className="min-w-0 truncate font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                {market.name}
              </span>
              <span className="shrink-0 font-[var(--cd-font-tabular)] text-[12.5px] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                {resolveOutcomeLabel(String(prediction.value), homeTeam, awayTeam)}
                <span className="ml-2 font-medium" style={{ color: 'var(--cd-accent)' }}>
                  {(prediction.probability * 100).toFixed(1)}%
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </CDPanel>
  )
}

/** Spec §16/§25 — the audit's own flagged issue: a Match Winner headline and a Correct Score
 * headline can read as contradictory (a favored side vs. a modal scoreline landing on a draw) even
 * though the two markets are independently modeled distributions, not competing claims about the
 * same thing. Only rendered when both market shapes are actually present, and every value quoted
 * here is real — this never asserts the models disagree, only that they answer different
 * questions. */
export function CrossMarketInterpretation({
  markets,
  latest,
  homeTeam,
  awayTeam,
  bare = false,
}: {
  markets: PredictionMarketDto[]
  latest: ReturnType<typeof latestByMarket>
  homeTeam: TeamRef
  awayTeam: TeamRef
  /** Skips the outer `CDPanel` — for a caller that already renders this inside its own card
   * (Competition Intelligence's per-fixture prediction card), so two panel borders never nest. */
  bare?: boolean
}) {
  const matchWinner = markets.find((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX))
  const correctScore = markets.find((m) => m.market_key.endsWith(CORRECT_SCORE_SUFFIX))
  if (!matchWinner || !correctScore) return null
  const matchWinnerPrediction = latest.get(matchWinner.id)!
  const correctScorePrediction = latest.get(correctScore.id)!

  const content = (
    <>
      <CDLabel>Market interpretation</CDLabel>
      <div className="mt-3 space-y-2 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
        <p>
          <span style={{ color: 'var(--cd-text-muted)' }}>Match Winner — TitanIQ's highest result probability: </span>
          <span style={{ color: 'var(--cd-text-primary)' }}>
            {resolveOutcomeLabel(String(matchWinnerPrediction.value), homeTeam, awayTeam)} ({(matchWinnerPrediction.probability * 100).toFixed(1)}%)
          </span>
        </p>
        <p>
          <span style={{ color: 'var(--cd-text-muted)' }}>Correct Score — most likely individual scoreline: </span>
          <span style={{ color: 'var(--cd-text-primary)' }}>
            {String(correctScorePrediction.value)} ({(correctScorePrediction.probability * 100).toFixed(1)}%)
          </span>
        </p>
        <p className="border-t pt-2" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
          These markets measure different probability distributions — the highest-probability match result does not necessarily
          correspond to the single highest-probability exact scoreline.
        </p>
      </div>
    </>
  )

  return bare ? content : <CDPanel padding="tight">{content}</CDPanel>
}

/** Real prediction-history aggregate — no backend endpoint sums this across many fixtures, so
 * it's derived client-side from a bounded fan-out of the same real `predictionsApi.review()` call
 * the Recently Completed Intelligence rails already use per fixture. Reused by both Team
 * (`PredictionIntelligenceSection`, renders nothing when genuinely empty — a lower-priority
 * sub-panel) and Competition Intelligence (renders `emptyState` instead — a top-level section
 * there, so silently vanishing would read as a missing feature rather than an honest absence). */
export function PredictionHistoryPanel({
  fixtures,
  emptyState,
}: {
  fixtures: FixtureSummaryDto[]
  /** Rendered instead of `null` when nothing has resolved yet, e.g. Competition Intelligence's
   * "Prediction performance unavailable" message — omit to just render nothing (Team Intelligence's
   * existing behavior, unchanged). */
  emptyState?: ReactNode
}) {
  const capped = fixtures.slice(0, HISTORY_FIXTURE_CAP)
  const reviewQueries = useQueries({
    queries: capped.map((fixture) => ({
      queryKey: ['predictions', 'review', fixture.id],
      queryFn: () => predictionsApi.review(fixture.id),
    })),
  })

  if (capped.length === 0) return emptyState ?? null
  if (reviewQueries.some((q) => q.isPending)) {
    return <InfinitySkeleton className="h-20" />
  }

  const metas = reviewQueries.map((q) => q.data?.meta).filter((m): m is NonNullable<typeof m> => !!m)
  const resolved = metas.reduce((sum, m) => sum + m.resolved_count, 0)
  const correct = metas.reduce((sum, m) => sum + m.correct_count, 0)
  const confidenceSamples = metas.filter((m) => m.average_confidence !== null).map((m) => m.average_confidence as number)
  const avgConfidence = confidenceSamples.length > 0 ? confidenceSamples.reduce((a, b) => a + b, 0) / confidenceSamples.length : null

  if (resolved === 0) return emptyState ?? null

  return (
    <CDPanel padding="tight">
      <div className="flex items-center gap-1.5">
        <TrendingUp className="size-3.5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Prediction intelligence</CDLabel>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-4">
        <div>
          <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Predictions analysed
          </dt>
          <dd className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {resolved}
          </dd>
        </div>
        <div>
          <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Historical accuracy
          </dt>
          <dd className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {Math.round((correct / resolved) * 100)}%
          </dd>
        </div>
        <div>
          <dt className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Avg. confidence
          </dt>
          <dd className="font-[var(--cd-font-tabular)] text-[18px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {avgConfidence !== null ? `${Math.round(avgConfidence * 100)}%` : 'Not available'}
          </dd>
        </div>
      </dl>
      <p className="mt-3 border-t pt-2 font-[var(--cd-font-body)] text-[10.5px]" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}>
        Across this team's {capped.length} most recent completed {capped.length === 1 ? 'fixture' : 'fixtures'} under TitanIQ coverage.
      </p>
    </CDPanel>
  )
}
