import { useMemo, useState, type ReactNode } from 'react'
import { UserRound, Radio } from 'lucide-react'
import { SPORT_SLUGS, type SportMeta } from '@/lib/hooks/use-sport'
import { usePlayerIntelligence, type EnrichedPlayer } from '@/lib/hooks/use-player-intelligence'
import { ErrorState } from '@/components/ui/error-state'
import { PlayerHero } from '@/components/command-deck/player-hero'
import { PlayerCard } from '@/components/command-deck/player-card'
import { PositionFilter } from '@/components/command-deck/position-filter'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { DomainKey } from '@/components/infinity/primitives/badge'

/** Same wider breakpoints as Team/Competition Intelligence's grids — these cards carry crest,
 * name, position, team link and a CTA, and truncate real player names at the generic grid's
 * 1024px 3-column density. */
function PlayerGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/**
 * Player Intelligence — the cross-sport nav destination (information-architecture restructure).
 * Reuses every piece the sport-scoped `/app/:sport/players` route already proved out
 * (`usePlayerIntelligence`, `PlayerCard`, `PositionFilter`) exactly the way `TeamsPage` reuses
 * `TeamCard`/`useTeamIntelligence` — only the sport-selection mechanism changes (local state +
 * `PlayerHero`'s now-optional `onSportChange`, instead of `SportShell`'s URL segment).
 */
export default function PlayersPage() {
  const [sport, setSport] = useState<SportMeta>(SPORT_SLUGS[0])
  const [search, setSearch] = useState('')
  const [position, setPosition] = useState<string | null>(null)

  const { players, aiReady, isLoading, isError, error, refetch } = usePlayerIntelligence(sport.code)
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  const backdropLogos = useMemo(
    () => [...new Set(players.map((p) => p.teamLogoUrl).filter((u): u is string => !!u))],
    [players],
  )

  const positionCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const p of players) {
      if (!p.position) continue
      counts.set(p.position, (counts.get(p.position) ?? 0) + 1)
    }
    return [...counts.entries()].sort(([, a], [, b]) => b - a).map(([pos, count]) => ({ position: pos, count }))
  }, [players])

  const positionFiltered = useMemo(() => (position ? players.filter((p) => p.position === position) : players), [players, position])

  const searching = search.trim().length > 0
  const searchResults = useMemo(() => {
    if (!searching) return []
    const q = search.trim().toLowerCase()
    return players.filter(
      (p) => p.name.toLowerCase().includes(q) || (p.team_name ?? '').toLowerCase().includes(q) || (p.position ?? '').toLowerCase().includes(q),
    )
  }, [players, search, searching])

  const liveNow = useMemo(() => players.filter((p) => p.teamLiveNow), [players])

  function cardFor(player: EnrichedPlayer) {
    return <PlayerCard key={player.id} player={player} sportSlug={sport.slug} sportDomain={domain} aiReady={aiReady} />
  }

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <PlayerHero sport={sport} onSportChange={setSport} search={search} onSearchChange={setSearch} backdropLogos={backdropLogos} />

      {isError && <ErrorState error={error} onRetry={() => void refetch()} />}

      {!isError && isLoading && <MissionSkeletonGrid count={6} />}

      {!isError && !isLoading && searching && (
        <MissionSection title={`Results for "${search.trim()}"`} subtitle={`${searchResults.length} player${searchResults.length === 1 ? '' : 's'} matched`}>
          {searchResults.length === 0 ? (
            <MissionEmptyState icon={UserRound} title="No players matched" description={`Nothing in ${sport.label} matches "${search.trim()}" — try a different search.`} />
          ) : (
            <PlayerGrid>{searchResults.map((p) => cardFor(p))}</PlayerGrid>
          )}
        </MissionSection>
      )}

      {!isError && !isLoading && !searching && (
        <>
          {liveNow.length > 0 && (
            <MissionSection title="Live Now" subtitle="Players whose team is on the pitch right now" icon={<Radio className="size-4" aria-hidden="true" />} domain={domain}>
              <PlayerGrid>{liveNow.map((p) => cardFor(p))}</PlayerGrid>
            </MissionSection>
          )}

          <MissionSection title={`${sport.label} Players`} subtitle={`Every ${sport.label} player under TitanIQ coverage`} icon={<UserRound className="size-4" aria-hidden="true" />}>
            {positionCounts.length > 0 && <div className="mb-4"><PositionFilter positionCounts={positionCounts} selected={position} onSelect={setPosition} sportDomain={domain} /></div>}
            {players.length === 0 ? (
              <MissionEmptyState icon={UserRound} title="No players found" description={`No ${sport.label} players are under coverage yet.`} />
            ) : positionFiltered.length === 0 ? (
              <MissionEmptyState icon={UserRound} title="No players found" description="Try another position filter." />
            ) : (
              <PlayerGrid>{positionFiltered.map((p) => cardFor(p))}</PlayerGrid>
            )}
          </MissionSection>
        </>
      )}
    </div>
  )
}
