import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { LiveDot } from '@/components/ui/live-dot'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { humanizeFactorKey } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

function formatKickoff(iso: string) {
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}

/**
 * The landing page's only match card — deliberately not `MatchIntelligenceCard` (that component
 * requires fabricated narrative fields — matchHighlight/newsHighlight/communityPulse/whyItMatters —
 * none of which `public_router.py`'s `featured-intelligence` returns). This renders only what the
 * endpoint actually provides: real teams, market, value, probability, confidence, and up to three
 * real evidence feature names — never invented explanatory prose (shape brief §10).
 */
export function PublicMatchCard({ pick }: { pick: PublicFeaturedIntelligenceDto }) {
  const sportSlug = SPORT_SLUGS.find((s) => s.code === pick.sport_code)?.slug ?? pick.sport_code
  const isLive = pick.status === 'live'

  return (
    <Link to={`/app/${sportSlug}/matches/${pick.fixture_id}`}>
      <Card
        rail={isLive ? 'live' : 'scheduled'}
        className="group flex h-full flex-col gap-4 p-5 transition-all duration-300 hover:border-border-strong hover:shadow-elevation-2 hover:-translate-y-1"
      >
        <div className="flex items-center justify-between gap-2">
          <span className="font-telemetry text-[11px] uppercase tracking-wider text-text-muted">
            {pick.competition_name ?? pick.sport_code}
          </span>
          {isLive ? (
            <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-live">
              <LiveDot /> Live
            </span>
          ) : (
            <span className="text-[11px] text-text-muted">{formatKickoff(pick.scheduled_at)}</span>
          )}
        </div>

        <p className="font-display text-base font-semibold text-text-primary">
          {pick.home_team?.short_name ?? pick.home_team?.name ?? 'TBD'} vs{' '}
          {pick.away_team?.short_name ?? pick.away_team?.name ?? 'TBD'}
        </p>

        <div className="flex items-center justify-between gap-3 rounded-md bg-bg-primary/60 px-3 py-2.5">
          <div className="min-w-0">
            <p className="truncate text-xs text-text-muted">{pick.market_name}</p>
            <p className="font-telemetry text-sm font-medium text-text-primary">
              {predictionValueLabel(pick.value, pick.home_team ?? undefined, pick.away_team ?? undefined)}
            </p>
          </div>
          <ConfidenceTelemetry confidence={pick.confidence_composite} size="sm" />
        </div>

        {(pick.evidence_highlights.supporting.length > 0 || pick.evidence_highlights.contradicting.length > 0) && (
          <div className="flex flex-1 flex-wrap items-start gap-1.5">
            {pick.evidence_highlights.supporting.map((feature) => (
              <span
                key={feature}
                className="rounded-full border border-confidence-high/40 bg-confidence-high/10 px-2 py-0.5 text-[10px] text-confidence-high"
              >
                {humanizeFactorKey(feature)}
              </span>
            ))}
            {pick.evidence_highlights.contradicting.map((feature) => (
              <span
                key={feature}
                className="rounded-full border border-border-default px-2 py-0.5 text-[10px] text-text-muted"
              >
                {humanizeFactorKey(feature)}
              </span>
            ))}
          </div>
        )}

        <span className="mt-auto inline-flex items-center gap-1 text-xs font-medium text-accent-primary opacity-0 transition-opacity group-hover:opacity-100">
          Open Match Intelligence <ArrowRight className="size-3" />
        </span>
      </Card>
    </Link>
  )
}
