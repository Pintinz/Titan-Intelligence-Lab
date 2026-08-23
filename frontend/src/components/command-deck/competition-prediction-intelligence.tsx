import { Link } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Sparkles, History } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { CDPanel, CDLabel } from './primitives/panel'
import { CDConfidenceGauge } from './primitives/gauge'
import { MissionEmptyState, MissionSkeletonGrid } from './mission-control/mission-section'
import {
  MATCH_WINNER_SUFFIX,
  CORRECT_SCORE_SUFFIX,
  CrossMarketInterpretation,
  PredictionFreshness,
  PredictionHistoryPanel,
} from './prediction-intelligence'
import { ActualVsPredictedCard } from './actual-vs-predicted-card'
import { latestByMarket } from './workspace/workspace-tabs'
import { resolveOutcomeLabel, type TeamRef } from '@/components/infinity/evidence-explorer'
import type { FixtureSummaryDto, PredictionMarketDto } from '@/lib/api/types'

/** Bounds the fixture-level prediction fan-out — a competition can have far more upcoming
 * fixtures than a single team, so this stays independently capped rather than trusting the
 * caller to have already bounded its list. */
const PREDICTED_FIXTURES_CAP = 8
/** Same reasoning, scoped to the recently-completed comparison strip below — a handful of the
 * most recent results is what "recently completed" means here, not every completed fixture the
 * competition has under coverage. */
const RECENT_COMPLETED_CAP = 4

/**
 * Competition Prediction Intelligence — real, already-generated predictions for this
 * competition's own upcoming fixtures (bounded fan-out over `predictionsApi.history`, same
 * technique `PredictionIntelligenceSection` uses for a single team's next fixture), plus the same
 * real Prediction History aggregate reused verbatim from Team Intelligence. Never generates a new
 * prediction and never shows a fixture with nothing generated for it.
 */
export function CompetitionPredictionIntelligence({
  upcomingFixtures,
  completedFixtures,
  markets,
  marketsLoading,
  sportSlug,
}: {
  upcomingFixtures: FixtureSummaryDto[]
  completedFixtures: FixtureSummaryDto[]
  markets: PredictionMarketDto[]
  marketsLoading: boolean
  sportSlug: string
}) {
  const candidates = upcomingFixtures.slice(0, PREDICTED_FIXTURES_CAP)
  const historyQueries = useQueries({
    queries: candidates.map((fixture) => ({
      queryKey: ['predictions', 'history', fixture.id],
      queryFn: () => predictionsApi.history(fixture.id),
    })),
  })

  return (
    <div className="space-y-6">
      <div>
        <div className="mb-3 flex items-center gap-2">
          <Sparkles className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <p className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            Predicted matches
          </p>
        </div>

        {marketsLoading || historyQueries.some((q) => q.isPending) ? (
          <MissionSkeletonGrid count={3} />
        ) : markets.length === 0 ? (
          <MissionEmptyState icon={Sparkles} title="Coverage building" description="TitanIQ has not yet trained a production market for this sport." />
        ) : (
          (() => {
            const cards = candidates
              .map((fixture, i) => {
                const latest = latestByMarket(historyQueries[i]?.data ?? [])
                const generatedMarkets = markets.filter((m) => latest.has(m.id))
                return { fixture, latest, generatedMarkets }
              })
              .filter((row) => row.generatedMarkets.length > 0)

            if (cards.length === 0) {
              return (
                <MissionEmptyState
                  icon={Sparkles}
                  title="No predicted matches yet"
                  description="TitanIQ hasn't generated predictions for this competition's upcoming fixtures yet."
                />
              )
            }

            return (
              <div className="grid gap-4 sm:grid-cols-2">
                {cards.map(({ fixture, latest, generatedMarkets }) => (
                  <PredictedFixtureCard key={fixture.id} fixture={fixture} latest={latest} generatedMarkets={generatedMarkets} sportSlug={sportSlug} />
                ))}
              </div>
            )
          })()
        )}
      </div>

      <RecentlyCompletedComparisons completedFixtures={completedFixtures} sportSlug={sportSlug} />

      <div>
        <PredictionHistoryPanel
          fixtures={completedFixtures}
          emptyState={
            <CDPanel padding="tight">
              <CDLabel>Prediction performance</CDLabel>
              <p className="mt-2 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                Prediction performance unavailable
              </p>
              <p className="mt-1 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
                No resolved production predictions are currently available for this competition.
              </p>
            </CDPanel>
          }
        />
      </div>
    </div>
  )
}

/** Phase 11 (post-match resolution pipeline, 2026-08-23) — the same "Upcoming Prediction →
 * Actual vs Predicted" transition Team Intelligence's `RecentResultComparison` shows, scoped to
 * this competition's own recently completed fixtures instead of one team's. Reuses
 * `ActualVsPredictedCard` directly — no second comparison rendering. Renders nothing at all when
 * none of the capped recent fixtures have a resolved prediction (an honest, common case; the
 * Prediction Performance panel below already covers "nothing resolved yet" with its own message). */
function RecentlyCompletedComparisons({ completedFixtures, sportSlug }: { completedFixtures: FixtureSummaryDto[]; sportSlug: string }) {
  const candidates = completedFixtures.slice(0, RECENT_COMPLETED_CAP)
  const reviewQueries = useQueries({
    queries: candidates.map((fixture) => ({
      queryKey: ['predictions', 'review', fixture.id],
      queryFn: () => predictionsApi.review(fixture.id),
    })),
  })

  if (candidates.length === 0 || reviewQueries.some((q) => q.isPending)) return null

  const cards = candidates
    .map((fixture, i) => {
      const markets = reviewQueries[i]?.data?.markets ?? []
      const primaryMarket = markets.find((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX)) ?? markets[0]
      return { fixture, primaryMarket }
    })
    .filter((row): row is { fixture: FixtureSummaryDto; primaryMarket: NonNullable<typeof row.primaryMarket> } => !!row.primaryMarket)

  if (cards.length === 0) return null

  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <History className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <p className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Recently completed
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {cards.map(({ fixture, primaryMarket }) => (
          <Link key={fixture.id} to={`/app/${fixture.sport_code ?? sportSlug}/matches/${fixture.id}/review`} className="block">
            <ActualVsPredictedCard
              fixture={fixture}
              market={primaryMarket}
              homeTeam={{ name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }}
              awayTeam={{ name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }}
            />
          </Link>
        ))}
      </div>
    </div>
  )
}

function PredictedFixtureCard({
  fixture,
  latest,
  generatedMarkets,
  sportSlug,
}: {
  fixture: FixtureSummaryDto
  latest: ReturnType<typeof latestByMarket>
  generatedMarkets: PredictionMarketDto[]
  sportSlug: string
}) {
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const primaryMarket = generatedMarkets.find((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX)) ?? generatedMarkets[0]
  const primaryPrediction = latest.get(primaryMarket.id)!
  const hasMatchWinner = generatedMarkets.some((m) => m.market_key.endsWith(MATCH_WINNER_SUFFIX))
  const hasCorrectScore = generatedMarkets.some((m) => m.market_key.endsWith(CORRECT_SCORE_SUFFIX))

  return (
    <CDPanel padding="tight">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/app/${fixture.sport_code ?? sportSlug}/matches/${fixture.id}`} className="min-w-0">
          <p className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
            {fixture.home_team.name} vs {fixture.away_team.name}
          </p>
          <p className="mt-0.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
            {new Date(fixture.scheduled_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}
          </p>
        </Link>
        <CDConfidenceGauge value={primaryPrediction.confidence_composite} size={40} />
      </div>

      <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <CDLabel>{primaryMarket.name}</CDLabel>
        <p className="mt-1 font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {resolveOutcomeLabel(String(primaryPrediction.value), homeTeam, awayTeam)}
          <span className="ml-2 font-[var(--cd-font-tabular)] text-[13px] font-normal tabular-nums" style={{ color: 'var(--cd-accent)' }}>
            {(primaryPrediction.probability * 100).toFixed(1)}%
          </span>
        </p>
        <div className="mt-1.5">
          <PredictionFreshness generatedAt={primaryPrediction.generated_at} />
        </div>
      </div>

      {hasMatchWinner && hasCorrectScore && (
        <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CrossMarketInterpretation markets={generatedMarkets} latest={latest} homeTeam={homeTeam} awayTeam={awayTeam} bare />
        </div>
      )}
    </CDPanel>
  )
}
