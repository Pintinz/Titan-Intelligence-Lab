import { Sparkles } from 'lucide-react'
import { DiscoveryMatchCard } from '../discovery/discovery-match-card'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'
import { fixtureScores } from '@/lib/sports-status'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { sportDomainFor } from '../primitives/domain'
import type { SportCode } from '@/lib/api/sports'
import type { FixtureCardItem } from './live-intelligence'

/**
 * AI Ready Fixtures — the page's primary section: today's non-live fixtures, falling back to the
 * soonest upcoming when nothing's scheduled today (same fallback rule the current Mission Control
 * already uses). Cinematic cards via `DiscoveryMatchCard`, capped at 6, "View all" to the full
 * Matches page for whichever sport contributed the first card.
 */
export function AiReadyFixtures({
  items,
  isLoading,
  isFallback,
  aiAvailableBySport,
}: {
  items: FixtureCardItem[]
  isLoading: boolean
  isFallback: boolean
  aiAvailableBySport: Set<SportCode>
}) {
  const watchlist = useWatchlist()
  const top = items.slice(0, 6)
  const viewAllHref = top[0] ? `/app/${top[0].sport.slug}/matches` : undefined

  return (
    <MissionSection
      id="ai-ready"
      title={isFallback ? 'Upcoming — AI ready fixtures' : "Today's AI ready fixtures"}
      subtitle="Fixtures with a trained market, ready for Generated Intelligence"
      icon={<Sparkles className="size-4" aria-hidden="true" />}
      domain="predictions"
      viewAllHref={viewAllHref}
    >
      {isLoading && <MissionSkeletonGrid />}
      {!isLoading && top.length === 0 && (
        <MissionEmptyState
          icon={Sparkles}
          title="Nothing scheduled right now."
          description="TitanIQ will surface the next AI-ready fixture the moment it's scheduled."
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
                status="upcoming"
                kickoffLabel={new Date(fixture.scheduled_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}
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
