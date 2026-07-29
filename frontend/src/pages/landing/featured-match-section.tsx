import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { Section, SectionHeading, IllustrativeTag, LiveDot } from './section-primitives'
import { FEATURED_MATCHES } from './sample-data'

function formatKickoff(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function FeaturedMatchSection() {
  return (
    <Section className="border-b border-border-subtle">
      <div className="flex items-end justify-between gap-4">
        <SectionHeading
          eyebrow="Featured Match Intelligence"
          title="The highest-intelligence matches right now"
          description="Not every fixture — only the matches where TitanIQ has the strongest evidence base and something worth explaining."
        />
        <IllustrativeTag />
      </div>

      <div className="-mx-6 flex snap-x snap-mandatory gap-4 overflow-x-auto px-6 pb-2 lg:-mx-10 lg:px-10">
        {FEATURED_MATCHES.map((m) => (
          <Card
            key={m.fixture.id}
            rail={m.rail}
            className="w-[320px] shrink-0 snap-start lg:w-[360px]"
          >
            <div className="flex flex-col gap-4 p-5">
              <div className="flex items-center justify-between">
                <span className="font-telemetry text-xs uppercase tracking-wider text-text-muted">
                  {m.sportLabel} · {m.fixture.competition_name}
                </span>
                {m.rail === 'live' ? (
                  <Badge variant="live" className="gap-1">
                    <LiveDot /> Live
                  </Badge>
                ) : (
                  <span className="font-mono text-xs text-text-muted">{formatKickoff(m.fixture.scheduled_at)}</span>
                )}
              </div>

              <p className="font-display text-base font-semibold text-text-primary">
                {m.fixture.home_team.name} vs {m.fixture.away_team.name}
              </p>

              <div className="flex items-center justify-between rounded-md bg-bg-primary px-3 py-2.5">
                <div>
                  <p className="text-xs text-text-muted">{m.market}</p>
                  <p className="font-telemetry text-sm font-medium text-text-primary">{m.pick}</p>
                </div>
                <ConfidenceTelemetry confidence={m.confidence.overall} size="sm" />
              </div>

              <dl className="space-y-2 text-xs">
                <div>
                  <dt className="font-medium text-text-muted">Match highlights</dt>
                  <dd className="text-text-secondary">{m.matchHighlight}</dd>
                </div>
                <div>
                  <dt className="font-medium text-text-muted">News highlights</dt>
                  <dd className="text-text-secondary">{m.newsHighlight}</dd>
                </div>
                <div>
                  <dt className="font-medium text-text-muted">Community pulse</dt>
                  <dd className="text-text-secondary">{m.communityPulse}</dd>
                </div>
                <div>
                  <dt className="font-medium text-text-muted">Why this match matters</dt>
                  <dd className="text-text-secondary">{m.whyItMatters}</dd>
                </div>
              </dl>

              <Link
                to="/signup"
                className="inline-flex items-center gap-1 text-sm font-medium text-accent-primary hover:text-accent-primary-hover"
              >
                Open Match Intelligence <ArrowRight className="size-3.5" />
              </Link>
            </div>
          </Card>
        ))}
      </div>

      <Link
        to="/signup"
        className="mt-8 inline-flex items-center gap-1.5 text-sm font-medium text-text-primary hover:text-accent-primary"
      >
        Explore all Intelligence <ArrowRight className="size-4" />
      </Link>
    </Section>
  )
}
