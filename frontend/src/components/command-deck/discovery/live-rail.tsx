import { useQuery } from '@tanstack/react-query'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureScores } from '@/lib/sports-status'
import { CDStatusDot } from '../primitives/status'
import { DiscoveryMatchCard } from './discovery-match-card'

/**
 * LiveRail — only renders when the sport actually has live fixtures right now (the common case
 * is zero). No empty carousel, no skeleton for a section that usually doesn't exist.
 */
export function LiveRail({
  sportSlug,
  sportCode,
  competitionId,
  aiAvailable,
  followingOnly,
}: {
  sportSlug: string
  sportCode: SportCode
  competitionId: string
  aiAvailable: boolean
  followingOnly: boolean
}) {
  const watchlist = useWatchlist()
  const query = useQuery({
    queryKey: ['sports', sportCode, 'fixtures', 'discovery-live', competitionId],
    queryFn: () => sportsApi.listFixturesPaged(sportCode, { status: 'live', competition_id: competitionId || undefined, limit: 12 }),
    refetchInterval: 30_000,
  })

  const items = (query.data?.items ?? []).filter((f) => !followingOnly || watchlist.isFollowing('fixture', f.id))
  if (items.length === 0) return null

  return (
    <section id="live" className="scroll-mt-24">
      <div className="mb-3 flex items-center gap-2.5">
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Live now
        </h3>
        <CDStatusDot label={`${items.length} live`} tone="live" />
      </div>
      <div className="-mx-1 flex snap-x gap-3.5 overflow-x-auto px-1 pb-1">
        {items.map((fixture) => {
          const { homeScore, awayScore } = fixtureScores(fixture.final_state)
          return (
            <div key={fixture.id} className="w-[280px] shrink-0 snap-start">
              <DiscoveryMatchCard
                competition={fixture.competition_name}
                competitionLogoUrl={fixture.competition_logo_url}
                status="live"
                venue={fixture.venue_name}
                homeTeam={fixture.home_team.name}
                awayTeam={fixture.away_team.name}
                homeScore={homeScore}
                awayScore={awayScore}
                homeLogoUrl={fixture.home_team.logo_url}
                awayLogoUrl={fixture.away_team.logo_url}
                aiAvailable={aiAvailable}
                following={watchlist.isFollowing('fixture', fixture.id)}
                onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
                href={`/app/${sportSlug}/matches/${fixture.id}`}
              />
            </div>
          )
        })}
      </div>
    </section>
  )
}
