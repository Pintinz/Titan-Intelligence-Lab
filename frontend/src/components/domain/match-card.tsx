import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowUpRight } from 'lucide-react'
import type { FixtureSummaryDto } from '@/lib/api/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'
import { transitionFast } from '@/lib/motion'
import { cn } from '@/lib/cn'

// Mirrors backend FixtureStatus (modules/sports/domain/value_objects.py) — "completed", not
// "finished".
const STATUS_VARIANT = {
  scheduled: 'neutral',
  live: 'danger',
  completed: 'success',
  postponed: 'warning',
  cancelled: 'neutral',
} as const

export function MatchCard({ fixture, className }: { fixture: FixtureSummaryDto; className?: string }) {
  const statusVariant = STATUS_VARIANT[fixture.status as keyof typeof STATUS_VARIANT] ?? 'neutral'
  const isLive = fixture.status === 'live'

  return (
    <motion.div whileHover={{ y: -3 }} transition={transitionFast} className="group">
      <Link to={`/app/matches/${fixture.id}`}>
        <Card
          className={cn(
            'flex flex-col gap-3 border-border-default p-4 transition-shadow group-hover:border-border-strong group-hover:shadow-[var(--shadow-elevation-2)]',
            className,
          )}
        >
          <div className="flex items-center justify-between text-xs text-text-muted">
            <span className="truncate">{fixture.competition_name}</span>
            <Badge variant={statusVariant} className={cn(isLive && 'animate-pulse')}>
              {fixture.status}
            </Badge>
          </div>
          <div className="flex items-center justify-between gap-2">
            <TeamRow id={fixture.home_team.id} name={fixture.home_team.name} shortName={fixture.home_team.short_name} />
            <span className="font-mono text-xs text-text-muted">vs</span>
            <TeamRow
              id={fixture.away_team.id}
              name={fixture.away_team.name}
              shortName={fixture.away_team.short_name}
              align="right"
            />
          </div>
          <div className="flex items-center justify-between">
            <p className="font-mono text-xs text-text-muted">{new Date(fixture.scheduled_at).toLocaleString()}</p>
            <span className="flex items-center gap-1 text-xs font-medium text-accent-primary opacity-0 transition-opacity group-hover:opacity-100">
              Analyze
              <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
            </span>
          </div>
        </Card>
      </Link>
    </motion.div>
  )
}

function TeamRow({ id, name, shortName, align = 'left' }: { id: string; name: string; shortName: string; align?: 'left' | 'right' }) {
  return (
    <div className={cn('flex min-w-0 flex-1 items-center gap-2', align === 'right' && 'flex-row-reverse text-right')}>
      <TeamMonogramBadge id={id} name={name} size={24} />
      <span className="truncate text-sm font-medium text-text-primary">{shortName}</span>
    </div>
  )
}
