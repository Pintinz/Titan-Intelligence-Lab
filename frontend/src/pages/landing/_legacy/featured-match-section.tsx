import { motion } from 'framer-motion'
import { MapPin } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ConfidenceRing } from '@/components/domain/confidence-ring'
import { RadarChartCard } from '@/components/domain/radar-chart'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { SAMPLE_FEATURED_PREDICTION, SAMPLE_FIXTURES } from '@/pages/landing/sample-data'
import { transitionSlow } from '@/lib/motion'
import type { ConfidenceBreakdownDto } from '@/lib/api/types'

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

function confidenceFactors(confidence: ConfidenceBreakdownDto): Record<string, number> {
  const { overall: _overall, ...factors } = confidence
  return factors
}

export function FeaturedMatchSection() {
  const fixture = SAMPLE_FIXTURES[0]
  const prediction = SAMPLE_FEATURED_PREDICTION

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="featured-match">
      <div className="mx-auto max-w-2xl text-center">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Match spotlight</span>
        <h2 className="mt-2 font-display text-3xl font-semibold text-text-primary">One match, fully explained</h2>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={transitionSlow}
        className="mt-10 overflow-hidden rounded-2xl border border-border-glass bg-bg-glass shadow-[var(--shadow-elevation-3)] backdrop-blur-[var(--blur-glass-md)]"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
      >
        <div className="flex flex-col items-center gap-6 p-8">
          <div className="flex items-center gap-2">
            <Badge variant="neutral">{fixture.competition_name}</Badge>
            <Badge variant="danger">{fixture.status}</Badge>
          </div>

          <div className="flex w-full max-w-lg items-center justify-between gap-4">
            <TeamHero id={fixture.home_team.id} name={fixture.home_team.name} score={1} />
            <span className="font-mono text-sm text-text-muted">vs</span>
            <TeamHero id={fixture.away_team.id} name={fixture.away_team.name} score={1} />
          </div>

          {fixture.venue_name && (
            <p className="flex items-center gap-1 text-sm text-text-muted">
              <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
              {fixture.venue_name}
            </p>
          )}
        </div>

        <div className="grid gap-6 border-t border-border-subtle bg-bg-primary/60 p-8 lg:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center gap-4">
            <ConfidenceRing value={prediction.confidence.overall} size={140} />
            <div className="text-center">
              <p className="font-mono text-lg font-semibold text-text-primary">
                {prediction.value} · {Math.round(prediction.probability * 100)}%
              </p>
              <p className="text-xs text-text-muted">model {prediction.model_version}</p>
            </div>
          </div>
          <div>
            <RadarChartCard data={confidenceFactors(prediction.confidence)} labels={CONFIDENCE_FACTOR_LABELS} height={240} />
            <p className="mt-3 text-sm text-text-secondary">{prediction.explanation.ai_explanation}</p>
          </div>
        </div>
      </motion.div>

      <p className="mt-4 text-center text-xs text-text-muted">
        Illustrative preview — the same confidence and explanation components rendered from real
        prediction data in Match Detail once signed in.
      </p>
    </section>
  )
}

function TeamHero({ id, name, score }: { id: string; name: string; score: number }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-2 text-center">
      <TeamMonogramBadge id={id} name={name} size={56} />
      <span className="font-display text-base font-semibold text-text-primary">{name}</span>
      <span className="font-mono text-2xl font-semibold text-text-primary">{score}</span>
    </div>
  )
}
