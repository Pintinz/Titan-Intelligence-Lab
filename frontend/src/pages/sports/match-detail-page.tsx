import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { MapPin, Sparkles } from 'lucide-react'
import { Breadcrumbs } from '@/components/ui/breadcrumbs'
import { PageLoader } from '@/components/layout/page-loader'
import { ErrorState } from '@/components/ui/error-state'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PredictionCard } from '@/components/domain/prediction-card'
import { ConfidenceRing } from '@/components/domain/confidence-ring'
import { RadarChartCard } from '@/components/domain/radar-chart'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { ExplanationDrawer } from '@/components/domain/explanation-drawer'
import { RelatedNewsPanel } from '@/components/domain/related-news-panel'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import type { ConfidenceBreakdownDto } from '@/lib/api/types'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { pageTransition } from '@/lib/motion'

const CONFIDENCE_FACTOR_LABELS: Record<string, string> = {
  data_quality: 'Data quality',
  feature_completeness: 'Feature completeness',
  model_certainty: 'Model certainty',
  historical_accuracy: 'Historical accuracy',
  sample_size_adequacy: 'Sample size',
  market_liquidity: 'Market liquidity',
  temporal_relevance: 'Temporal relevance',
  ensemble_agreement: 'Ensemble agreement',
  calibration_quality: 'Calibration quality',
  volatility_penalty: 'Volatility penalty',
}

/**
 * Flagship match page. Composes only what real backend data supports:
 *  - sportsApi.getFixture (team names/ids, competition, venue, scheduled time, status, final_state)
 *  - predictionsApi.history(fixture.id) — subject_ref for a prediction is the stringified fixture
 *    id (backend/modules/predictions/domain/entities.py), so this is a real, correct linkage.
 * Deliberately NOT shown (disclosed gaps, not faked): weather (no field anywhere in the backend),
 * a match-events timeline (the `matchEvents` realtime channel is subscribed below for when events
 * exist server-side, but none are populated yet), player ratings (no rating field on
 * PlayerSummaryDto), and standings (FixtureSummaryDto has no competition_id, only a name string —
 * standings stay correctly linked on competition-detail-page.tsx where a real id exists).
 */
export default function MatchDetailPage() {
  const { matchId } = useParams<{ matchId: string }>()
  const [drawerOpen, setDrawerOpen] = useState(false)

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', matchId],
    queryFn: () => sportsApi.getFixture(matchId!),
    enabled: Boolean(matchId),
  })

  const predictionsQuery = useQuery({
    queryKey: ['predictions', 'history', matchId],
    queryFn: () => predictionsApi.history(matchId!),
    enabled: Boolean(matchId),
  })

  useRealtimeInvalidate('matches', [['sports', 'fixture', matchId]])
  useRealtimeInvalidate('matchEvents', [['sports', 'fixture', matchId]])
  useRealtimeInvalidate('predictions', [['predictions', 'history', matchId]])

  if (fixtureQuery.isLoading) return <PageLoader />
  if (fixtureQuery.isError || !fixtureQuery.data) {
    return (
      <div className="p-6">
        <ErrorState description="Could not load this match." onRetry={() => fixtureQuery.refetch()} />
      </div>
    )
  }

  const fixture = fixtureQuery.data
  const latestPrediction = predictionsQuery.data?.[0]
  const score = fixture.final_state && typeof fixture.final_state === 'object' ? (fixture.final_state as Record<string, unknown>) : null

  return (
    <motion.div variants={pageTransition} initial="initial" animate="animate" className="flex flex-col gap-6 p-6">
      <Breadcrumbs
        items={[
          { label: 'Dashboard', to: '/app' },
          { label: 'Match Center', to: '/app/matches' },
          { label: `${fixture.home_team.short_name} vs ${fixture.away_team.short_name}` },
        ]}
      />

      <div
        className="overflow-hidden rounded-xl border border-border-glass bg-bg-glass shadow-[var(--shadow-elevation-2)] backdrop-blur-[var(--blur-glass-md)]"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
      >
        <div className="flex flex-col items-center gap-6 p-8">
          <div className="flex items-center gap-2">
            <Badge variant="neutral">{fixture.competition_name}</Badge>
            <Badge variant={fixture.status === 'live' ? 'danger' : 'neutral'}>{fixture.status}</Badge>
          </div>

          <div className="flex w-full max-w-lg items-center justify-between gap-4">
            <TeamHero id={fixture.home_team.id} name={fixture.home_team.name} scoreKey="home_score" score={score} />
            <span className="font-mono text-sm text-text-muted">vs</span>
            <TeamHero id={fixture.away_team.id} name={fixture.away_team.name} scoreKey="away_score" score={score} />
          </div>

          <div className="flex flex-col items-center gap-1 text-center text-sm text-text-secondary">
            <p className="font-mono">{new Date(fixture.scheduled_at).toLocaleString()}</p>
            {fixture.venue_name && (
              <p className="flex items-center gap-1 text-text-muted">
                <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                {fixture.venue_name}
              </p>
            )}
          </div>
        </div>
      </div>

      {latestPrediction ? (
        <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
          <Card>
            <CardHeader>
              <CardTitle>Confidence</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center gap-4 py-6">
              <ConfidenceRing value={latestPrediction.confidence.overall} size={140} />
              <RadarChartCard data={confidenceFactors(latestPrediction.confidence)} labels={CONFIDENCE_FACTOR_LABELS} height={220} />
              <ExplanationDrawer
                confidence={latestPrediction.confidence}
                explanation={latestPrediction.explanation}
                open={drawerOpen}
                onOpenChange={setDrawerOpen}
                trigger={
                  <Button variant="secondary" size="sm" className="w-full">
                    <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                    Full AI explanation
                  </Button>
                }
              />
            </CardContent>
          </Card>
          <PredictionCard prediction={latestPrediction} />
        </div>
      ) : (
        !predictionsQuery.isLoading && (
          <Card>
            <CardContent className="p-6 text-center text-sm text-text-muted">
              No prediction has been generated for this match yet.
            </CardContent>
          </Card>
        )
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <RelatedNewsPanel entityRef={fixture.home_team.name} />
        <RelatedNewsPanel entityRef={fixture.away_team.name} />
      </div>
    </motion.div>
  )
}

function TeamHero({ id, name, score, scoreKey }: { id: string; name: string; score: Record<string, unknown> | null; scoreKey: string }) {
  const value = score?.[scoreKey]
  return (
    <div className="flex flex-1 flex-col items-center gap-2 text-center">
      <TeamMonogramBadge id={id} name={name} size={56} />
      <span className="font-display text-base font-semibold text-text-primary">{name}</span>
      {typeof value === 'number' && <span className="font-mono text-2xl font-semibold text-text-primary">{value}</span>}
    </div>
  )
}

function confidenceFactors(confidence: ConfidenceBreakdownDto): Record<string, number> {
  const { overall: _overall, ...factors } = confidence
  return factors
}
