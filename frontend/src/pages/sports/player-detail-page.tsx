import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { useSportParam } from '@/lib/hooks/use-sport'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityPanel, InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import type { DomainKey } from '@/components/infinity/primitives/badge'

export default function PlayerDetailPage() {
  const sport = useSportParam()
  const { playerId } = useParams<{ playerId: string }>()

  const { data: player, isPending, isError, error, refetch } = useQuery({
    queryKey: ['sports', 'player', playerId],
    queryFn: () => sportsApi.getPlayer(playerId!),
    enabled: !!playerId,
  })

  if (!sport) return null
  if (isPending) {
    return (
      <div className="space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-32" />
      </div>
    )
  }
  if (isError) return <ErrorState error={error} onRetry={() => void refetch()} />

  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  return (
    <div className="max-w-2xl space-y-6">
      <Link
        to={`/app/${sport.slug}/players`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to players
      </Link>

      <InfinityPanel tone={`var(--infinity-domain-${domain})`}>
        <InfinityLabel tone={`var(--infinity-domain-${domain})`}>Player Intelligence</InfinityLabel>
        <h1 className="mt-2 font-infinity-display text-2xl font-semibold text-infinity-text-primary sm:text-3xl">{player.name}</h1>

        <dl className="mt-6 grid grid-cols-2 gap-5 border-t border-infinity-border-hairline pt-5 sm:grid-cols-3">
          <div>
            <dt className="font-infinity-body text-[11px] uppercase tracking-[0.06em] text-infinity-text-muted">Position</dt>
            <dd className="mt-1 font-infinity-body text-[14px] text-infinity-text-primary">{player.position ?? 'Unknown'}</dd>
          </div>
          <div>
            <dt className="font-infinity-body text-[11px] uppercase tracking-[0.06em] text-infinity-text-muted">Team</dt>
            <dd className="mt-1 font-infinity-body text-[14px] text-infinity-text-primary">
              {player.team_id ? (
                <Link to={`/app/${sport.slug}/teams/${player.team_id}`} className="text-infinity-signal hover:text-infinity-signal-hover">
                  {player.team_name ?? 'View team'}
                </Link>
              ) : (
                'Unassigned'
              )}
            </dd>
          </div>
          <div>
            <dt className="font-infinity-body text-[11px] uppercase tracking-[0.06em] text-infinity-text-muted">Date of birth</dt>
            <dd className="mt-1 font-infinity-mono text-[13px] tabular-nums text-infinity-text-primary">
              {player.date_of_birth ? new Date(player.date_of_birth).toLocaleDateString() : 'Unknown'}
            </dd>
          </div>
        </dl>
      </InfinityPanel>
    </div>
  )
}
