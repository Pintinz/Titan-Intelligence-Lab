import { Link } from 'react-router-dom'
import { User } from 'lucide-react'
import type { PlayerSummaryDto } from '@/lib/api/types'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

export function PlayerCard({ player }: { player: PlayerSummaryDto }) {
  return (
    <Link to={`/app/players/${player.id}`}>
      <Card className="flex items-center gap-3 p-4 transition-colors hover:border-border-strong">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-bg-secondary text-text-muted">
          <User className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-text-primary">{player.name}</p>
          <p className="truncate text-xs text-text-muted">{player.team_name ?? 'Free agent'}</p>
        </div>
        {player.position && <Badge variant="neutral">{player.position}</Badge>}
      </Card>
    </Link>
  )
}
