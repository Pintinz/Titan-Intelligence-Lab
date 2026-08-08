import { Radio } from 'lucide-react'
import { CDStatusDot } from '../primitives/status'
import { DiscoveryMatchCard } from '../discovery/discovery-match-card'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import { fixtureScores } from '@/lib/sports-status'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { sportDomainFor } from '../primitives/domain'
import type { FixtureSummaryDto } from '@/lib/api/types'
import type { SportCode } from '@/lib/api/sports'
import type { SportMeta } from '@/lib/hooks/use-sport'

/**
 * Live Intelligence — highest priority section. Only ever the common case (zero live fixtures)
 * gets the brief's exact honest copy, never a bare "No live matches." Cross-sport: every fixture
 * here already carries which sport it belongs to (`FixtureCardItem.sport`), fetched once by the
 * page (no per-section refetch).
 */
export interface FixtureCardItem {
  fixture: FixtureSummaryDto
  sport: SportMeta
}

export function LiveIntelligence({
  items,
  isLoading,
  aiAvailableBySport,
}: {
  items: FixtureCardItem[]
  isLoading: boolean
  aiAvailableBySport: Set<SportCode>
}) {
  const watchlist = useWatchlist()
  const top = items.slice(0, 6)

  return (
    <MissionSection
      id="live"
      title="Live Intelligence"
      subtitle="Matches under live AI monitoring right now"
      icon={<Radio className="size-4" aria-hidden="true" />}
      status={top.length > 0 ? <CDStatusDot label={`${items.length} live`} tone="live" /> : undefined}
      viewAllHref={items.length > 0 ? '/app/live' : undefined}
    >
      {isLoading && <MissionSkeletonGrid />}
      {!isLoading && top.length === 0 && (
        <MissionEmptyState
          icon={Radio}
          title="TitanIQ is monitoring every supported competition."
          description="Live intelligence will automatically appear when matches begin."
          actionLabel="Browse upcoming fixtures"
          actionHref="#ai-ready"
        />
      )}
      {!isLoading && top.length > 0 && (
        <MissionCardGrid>
          {top.map(({ fixture, sport }) => {
            const { homeScore, awayScore } = fixtureScores(fixture.final_state)
            return (
              <DiscoveryMatchCard
                key={fixture.id}
                competition={fixture.competition_name}
                competitionLogoUrl={fixture.competition_logo_url}
                status="live"
                venue={fixture.venue_name}
                homeTeam={fixture.home_team?.name ?? 'TBD'}
                awayTeam={fixture.away_team?.name ?? 'TBD'}
                homeScore={homeScore}
                awayScore={awayScore}
                homeLogoUrl={fixture.home_team?.logo_url}
                awayLogoUrl={fixture.away_team?.logo_url}
                aiAvailable={aiAvailableBySport.has(sport.code)}
                sportDomain={sportDomainFor(sport.slug)}
                following={watchlist.isFollowing('fixture', fixture.id)}
                onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
                href={`/app/${sport.slug}/matches/${fixture.id}`}
              />
            )
          })}
        </MissionCardGrid>
      )}
    </MissionSection>
  )
}
