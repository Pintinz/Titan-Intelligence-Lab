import { Link } from 'react-router-dom'
import { ArrowRight, TrendingUp } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ConfidenceTelemetry } from '@/components/domain/confidence-telemetry'
import { LiveDot } from '@/components/ui/live-dot'
import type { FixtureSummaryDto } from '@/lib/api/types'

interface MatchIntelligenceCardProps {
  fixture: FixtureSummaryDto
  sportLabel: string
  sportSlug: string
  market: string
  pick: string
  confidence: number
  matchHighlight: string
  newsHighlight: string
  communityPulse: string
  whyItMatters: string
  rail?: 'live' | 'scheduled' | 'completed'
  communitySignalCount?: number
  communitySignalSentiment?: string
  hasNews?: boolean
  lastUpdated?: string
}

function formatKickoff(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function MatchIntelligenceCard({
  fixture,
  sportLabel,
  sportSlug,
  market,
  pick,
  confidence,
  matchHighlight,
  newsHighlight,
  communityPulse,
  whyItMatters,
  rail = 'scheduled',
  communitySignalCount,
  hasNews,
  lastUpdated,
}: MatchIntelligenceCardProps) {
  return (
    <Link to={`/app/${sportSlug}/matches/${fixture.id}`}>
      <Card
        rail={rail}
        className="group h-full transition-all duration-300 hover:border-border-strong hover:shadow-elevation-2 hover:-translate-y-1 animate-card-entrance"
      >
        <div className="flex flex-col gap-5 p-5">
          {/* Header: Sport + Competition + Status */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <span className="font-telemetry text-xs uppercase tracking-wider text-text-muted">
                {sportLabel} · {fixture.competition_name}
              </span>
            </div>
            {rail === 'live' ? (
              <Badge variant="live" className="gap-1 shrink-0">
                <LiveDot /> Live
              </Badge>
            ) : (
              <span className="font-mono text-xs text-text-muted shrink-0">
                {formatKickoff(fixture.scheduled_at)}
              </span>
            )}
          </div>

          {/* Team Matchup with Avatars */}
          <div className="flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <p className="font-display text-lg font-semibold text-text-primary leading-tight">
                <span className="truncate block">{fixture.home_team.name}</span>
              </p>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-bg-secondary text-xs font-semibold text-text-primary">
              {fixture.home_team.short_name?.charAt(0) || 'H'}
            </div>
            <span className="text-xs font-medium text-text-muted">vs</span>
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-bg-secondary text-xs font-semibold text-text-primary">
              {fixture.away_team.short_name?.charAt(0) || 'A'}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display text-lg font-semibold text-text-primary leading-tight">
                <span className="truncate block text-right">{fixture.away_team.name}</span>
              </p>
            </div>
          </div>

          {/* Market + Prediction + Confidence */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-muted">{market}</span>
              <ConfidenceTelemetry confidence={confidence} size="sm" />
            </div>
            <div className="group/pick rounded-lg border border-accent-primary-muted bg-gradient-to-r from-accent-primary-muted to-transparent px-4 py-3 backdrop-blur-sm transition-all duration-300 group-hover:border-accent-primary group-hover:bg-gradient-to-r group-hover:from-accent-primary-muted group-hover:to-accent-primary-muted/50">
              <p className="font-telemetry text-base font-medium text-accent-primary group-hover/pick:text-accent-primary-hover transition-colors">{pick}</p>
            </div>
          </div>

          {/* Intelligence Highlights */}
          <div className="space-y-2 border-t border-border-subtle pt-4">
            <div className="grid grid-cols-2 gap-3">
              {/* Match Highlight */}
              <div className="rounded-md bg-bg-primary p-3">
                <p className="font-medium text-xs text-text-muted mb-1">Form</p>
                <p className="text-xs leading-relaxed text-text-secondary line-clamp-2">
                  {matchHighlight}
                </p>
              </div>

              {/* News Indicator */}
              {hasNews && (
                <div className="rounded-md bg-bg-primary p-3 border border-accent-secondary-muted">
                  <div className="flex items-start justify-between mb-1">
                    <p className="font-medium text-xs text-text-muted">News</p>
                    <TrendingUp className="w-3 h-3 text-accent-secondary" />
                  </div>
                  <p className="text-xs leading-relaxed text-text-secondary line-clamp-2">
                    {newsHighlight}
                  </p>
                </div>
              )}
            </div>

            {/* Community Pulse */}
            <div className="rounded-md bg-bg-primary p-3 border border-border-subtle">
              <div className="flex items-center justify-between mb-1">
                <p className="font-medium text-xs text-text-muted">Community</p>
                {communitySignalCount && (
                  <span className="text-xs text-text-secondary">
                    {communitySignalCount.toLocaleString()} signals
                  </span>
                )}
              </div>
              <p className="text-xs leading-relaxed text-text-secondary">
                {communityPulse}
              </p>
            </div>
          </div>

          {/* Why It Matters */}
          <div className="space-y-2 border-t border-border-subtle pt-4">
            <p className="text-xs font-medium text-text-muted">Why this match matters</p>
            <p className="text-xs leading-relaxed text-text-secondary">
              {whyItMatters}
            </p>
          </div>

          {/* CTA */}
          <div className="border-t border-border-subtle pt-4 mt-auto">
            <div className="inline-flex items-center gap-1 text-sm font-medium text-accent-primary group-hover:text-accent-primary-hover transition-colors">
              Open Match Intelligence <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" />
            </div>
          </div>

          {/* Metadata Footer */}
          {lastUpdated && (
            <div className="text-xs text-text-muted border-t border-border-subtle pt-3">
              Last updated {lastUpdated}
            </div>
          )}
        </div>
      </Card>
    </Link>
  )
}
