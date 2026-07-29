import { Link } from 'react-router-dom'
import { Shield } from 'lucide-react'
import type { TeamSummaryDto } from '@/lib/api/types'
import { Card } from '@/components/ui/card'

export function TeamCard({ team }: { team: TeamSummaryDto }) {
  return (
    <Link to={`/app/teams/${team.id}`}>
      <Card className="flex items-center gap-3 p-4 transition-colors hover:border-border-strong">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bg-secondary text-text-muted">
          <Shield className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text-primary">{team.name}</p>
          <p className="text-xs text-text-muted">{team.country ?? '—'}</p>
        </div>
      </Card>
    </Link>
  )
}
