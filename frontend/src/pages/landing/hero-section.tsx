import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { LiveDot } from '@/components/ui/live-dot'
import { IllustrativeTag } from './section-primitives'
import { FEATURED_MATCHES } from './sample-data'

const heroMatch = FEATURED_MATCHES[0]

export function HeroSection() {
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
              <Link to="/methodology">See the methodology</Link>
            </Button>
          </div>
        </div>

        <div className="relative">
          <div className="rounded-lg border border-border-default bg-bg-elevated/80 p-5 shadow-[var(--shadow-elevation-3)] backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <span className="font-telemetry text-xs uppercase tracking-wider text-text-muted">
                {heroMatch.sportLabel} · {heroMatch.fixture.competition_name}
              </span>
              <IllustrativeTag />
            </div>
            <p className="mt-3 font-display text-lg font-semibold text-text-primary">
              {heroMatch.fixture.home_team.short_name} vs {heroMatch.fixture.away_team.short_name}
            </p>
            <div className="mt-4 flex items-center justify-between rounded-md bg-bg-primary/60 px-3 py-2.5">
              <div>
                <p className="text-xs text-text-muted">{heroMatch.market}</p>
                <p className="font-telemetry text-base font-medium text-text-primary">{heroMatch.pick}</p>
              </div>
              <ConfidenceTelemetry confidence={heroMatch.confidence.composite} />
            </div>
            <p className="mt-4 text-sm text-text-secondary">{heroMatch.whyItMatters}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
