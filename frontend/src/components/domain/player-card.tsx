import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/card'
import type { PlayerSummaryDto } from '@/lib/api/types'

export function PlayerCard({ player, sportSlug }: { player: PlayerSummaryDto; sportSlug: string }) {
  return (
    <Link to={`/app/${sportSlug}/players/${player.id}`}>
      <Card className="h-full transition-colors hover:border-border-strong">
        <div className="flex flex-col gap-1 p-4">
          <p className="truncate font-display text-sm font-semibold text-text-primary">{player.name}</p>
          <p className="truncate text-xs text-text-muted">
            {[player.position, player.team_name].filter(Boolean).join(' · ') || 'Unassigned'}
          </p>
        </div>
      </Card>
    </Link>
  )
}
