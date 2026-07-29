import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/ui/error-state'
import { Card } from '@/components/ui/card'

export default function PlayerDetailPage() {
  const sport = useSportParam()
  const { playerId } = useParams<{ playerId: string }>()

  const { data: player, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'player', playerId],
    queryFn: () => sportsApi.getPlayer(playerId!),
    enabled: !!playerId,
  })

  if (!sport) return null
  if (isPending) return <Skeleton className="h-40" />
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <Link
          to={`/app/${sport.slug}/players`}
          className="inline-flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
        >
          <ArrowLeft className="size-3.5" /> Back to players
        </Link>
        <p className="mt-3 font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          Player Intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-semibold text-text-primary">{player.name}</h1>
      </div>

      <Card className="p-5">
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-xs text-text-muted">Position</dt>
            <dd className="text-text-primary">{player.position ?? 'Unknown'}</dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Team</dt>
            <dd className="text-text-primary">
              {player.team_id ? (
                <Link to={`/app/${sport.slug}/teams/${player.team_id}`} className="text-accent-primary hover:text-accent-primary-hover">
                  {player.team_name ?? 'View team'}
                </Link>
              ) : (
                'Unassigned'
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-text-muted">Date of birth</dt>
            <dd className="text-text-primary">
              {player.date_of_birth ? new Date(player.date_of_birth).toLocaleDateString() : 'Unknown'}
            </dd>
          </div>
        </dl>
      </Card>
    </div>
  )
}
