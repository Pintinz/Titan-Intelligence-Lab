import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { LiveDot } from '@/components/ui/live-dot'
import type { FixtureSummaryDto } from '@/lib/api/types'

function railFor(status: string): 'live' | 'scheduled' | 'completed' {
  const s = status.toLowerCase()
  if (s === 'live' || s === 'in_play') return 'live'
  if (s === 'finished' || s === 'completed' || s === 'ft') return 'completed'
  return 'scheduled'
}

function formatKickoff(iso: string) {
  return new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
}

export function FixtureCard({ fixture, sportSlug }: { fixture: FixtureSummaryDto; sportSlug: string }) {
  const rail = railFor(fixture.status)

  return (
    <Link to={`/app/${sportSlug}/matches/${fixture.id}`}>
      <Card rail={rail} className="h-full transition-colors hover:border-border-strong">
        <div className="flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between">
            <span className="truncate font-telemetry text-xs uppercase tracking-wider text-text-muted">
              {fixture.competition_name}
            </span>
            {rail === 'live' ? (
              <Badge variant="live" className="shrink-0 gap-1">
                <LiveDot /> Live
              </Badge>
            ) : (
              <span className="shrink-0 font-mono text-xs text-text-muted">{formatKickoff(fixture.scheduled_at)}</span>
            )}
          </div>
          <p className="font-display text-sm font-semibold text-text-primary">
            {fixture.home_team.name} vs {fixture.away_team.name}
          </p>
          {fixture.venue_name && <p className="text-xs text-text-muted">{fixture.venue_name}</p>}
        </div>
      </Card>
    </Link>
  )
}
