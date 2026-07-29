import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import type { TeamSummaryDto } from '@/lib/api/types'

export function TeamCard({ team, sportSlug }: { team: TeamSummaryDto; sportSlug: string }) {
  return (
    <Link to={`/app/${sportSlug}/teams/${team.id}`}>
      <Card className="h-full transition-colors hover:border-border-strong">
        <div className="flex items-center gap-3 p-4">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent-primary-muted font-mono text-sm font-medium text-accent-primary">
            {team.short_name.slice(0, 3).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate font-display text-sm font-semibold text-text-primary">{team.name}</p>
            {team.country && <p className="truncate text-xs text-text-muted">{team.country}</p>}
          </div>
        </div>
      </Card>
    </Link>
  )
}
