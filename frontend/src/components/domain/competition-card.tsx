import { Link } from 'react-router-dom'
import { Trophy } from 'lucide-react'
import type { CompetitionSummaryDto } from '@/lib/api/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function CompetitionCard({ competition }: { competition: CompetitionSummaryDto }) {
  return (
    <Link to={`/app/competitions/${competition.id}`}>
      <Card className="flex items-center gap-3 p-4 transition-colors hover:border-border-strong">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bg-secondary text-text-muted">
          <Trophy className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text-primary">{competition.name}</p>
          <p className="text-xs text-text-muted">{competition.country ?? 'International'}</p>
        </div>
        <Badge variant="neutral">{competition.type}</Badge>
      </Card>
    </Link>
  )
}
