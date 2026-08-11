import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { LiveDot } from '@/components/ui/live-dot'
import { humanizeFactorKey } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

/**
 * The hero's "Intelligence Core" — a real currently-published pick when one exists, or an honest
 * neutral platform-state visualization when it doesn't (shape brief §8: never fabricate a match to
 * fill the space). `pick` is the highest-confidence entry from `featured-intelligence`, or `null`
 * while loading / if none is currently published.
 */
export function HeroSection({ loading, pick }: { loading: boolean; pick: PublicFeaturedIntelligenceDto | null }) {
  return (
    <div className="relative overflow-hidden border-b border-border-subtle">
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        style={{ backgroundImage: 'var(--gradient-mesh-hero)' }}
        aria-hidden="true"
      />
      <div className="relative mx-auto grid max-w-6xl gap-14 px-6 py-20 lg:grid-cols-[1.1fr_0.9fr] lg:px-10 lg:py-28">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-border-default bg-bg-elevated/60 px-3 py-1 text-xs font-medium text-text-secondary">
            <LiveDot />
            Sports Intelligence Platform — not a prediction site
          </p>
          <h1 className="mt-6 max-w-xl font-display text-4xl font-semibold leading-[1.05] tracking-tight text-text-primary lg:text-6xl">
            See Every Match Through Intelligence.
          </h1>
          <p className="mt-6 max-w-lg text-lg text-text-secondary">
            TitanIQ converts structured data, live events, news, and community signal into
            explainable sports intelligence — every output carries its confidence, its evidence,
            and the reasoning behind it. Predictions are one output; they were never the point.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button asChild size="lg">
              <Link to="/signup">Start free</Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link to="/methodology">Explore the methodology</Link>
            </Button>
          </div>
        </div>

        <div className="relative">
          <div className="rounded-lg border border-border-default bg-bg-elevated/80 p-5 shadow-[var(--shadow-elevation-3)] backdrop-blur-sm">
            {loading ? (
              <div className="animate-pulse space-y-4">
                <div className="h-3 w-32 rounded bg-bg-secondary" />
                <div className="h-5 w-48 rounded bg-bg-secondary" />
                <div className="h-14 rounded-md bg-bg-secondary" />
              </div>
            ) : pick ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="font-telemetry text-xs uppercase tracking-wider text-text-muted">
                    {pick.sport_code} · {pick.competition_name ?? 'Intelligence'}
                  </span>
                  {pick.status === 'live' && (
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-live">
                      <LiveDot /> Live
                    </span>
                  )}
                </div>
                <p className="mt-3 font-display text-lg font-semibold text-text-primary">
                  {pick.home_team?.short_name ?? pick.home_team?.name} vs{' '}
                  {pick.away_team?.short_name ?? pick.away_team?.name}
                </p>
                <div className="mt-4 flex items-center justify-between rounded-md bg-bg-primary/60 px-3 py-2.5">
                  <div>
                    <p className="text-xs text-text-muted">{pick.market_name}</p>
                    <p className="font-telemetry text-base font-medium text-text-primary">
                      {predictionValueLabel(pick.value, pick.home_team ?? undefined, pick.away_team ?? undefined)}
                    </p>
                  </div>
                  <ConfidenceTelemetry confidence={pick.confidence_composite} />
                </div>
                {pick.evidence_highlights.supporting.length > 0 && (
                  <p className="mt-4 text-sm text-text-secondary">
                    Backed by {pick.evidence_highlights.supporting.map(humanizeFactorKey).join(', ')}.
                  </p>
                )}
              </>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <span className="font-telemetry text-xs uppercase tracking-wider text-text-muted">
                    Intelligence Engine
                  </span>
                </div>
                <p className="mt-3 font-display text-lg font-semibold text-text-primary">
                  Awaiting published intelligence
                </p>
                <p className="mt-3 text-sm text-text-secondary">
                  The engine publishes a prediction only once it clears its confidence threshold —
                  nothing ships without evidence behind it.
                </p>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
