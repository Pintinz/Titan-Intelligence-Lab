import { useMemo, useState, type ReactNode } from 'react'
import { Radio, CalendarDays, CheckCircle2 } from 'lucide-react'
import { SPORT_SLUGS, type SportMeta } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useMatchIntelligence } from '@/lib/hooks/use-match-intelligence'
import { fixtureScores } from '@/lib/sports-status'
import { ErrorState } from '@/components/ui/error-state'
import { MatchesHero } from '@/components/command-deck/matches-hero'
import { DiscoveryMatchCard } from '@/components/command-deck/discovery/discovery-match-card'
import { MissionSection, MissionSkeletonGrid, MissionEmptyState } from '@/components/command-deck/mission-control/mission-section'
import type { DomainKey } from '@/components/infinity/primitives/badge'
import type { FixtureSummaryDto } from '@/lib/api/types'

/** Same wider breakpoints as Team/Competition/Player Intelligence's grids. */
function MatchGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
}

/**
 * Matches — the cross-sport nav destination (information-architecture restructure). Discovery
 * only, per the shaped brief: find a match, see if TitanIQ has intelligence for it, open it —
 * not a second Intelligence Center. Deeper per-sport tooling (Trending, Competition filter chips,
 * date-scoped "view all" pages) stays on `/app/:sport/matches`, reached from any card's
 * competition/team context here, not duplicated on this entry point.
 */
export default function MatchesPage() {
  const [sport, setSport] = useState<SportMeta>(SPORT_SLUGS[0])
  const [search, setSearch] = useState('')
  const watchlist = useWatchlist()

  const { live, upcoming, completed, aiReady, isLoading, isError, error, refetch } = useMatchIntelligence(sport.code)
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

  const all = useMemo(() => [...live, ...upcoming, ...completed], [live, upcoming, completed])
  const backdropLogos = useMemo(
    () => [...new Set(all.flatMap((f) => [f.home_team.logo_url, f.away_team.logo_url]).filter((u): u is string => !!u))],
    [all],
  )

  const searching = search.trim().length > 0
  const searchResults = useMemo(() => {
    if (!searching) return []
    const q = search.trim().toLowerCase()
    return all.filter(
      (f) =>
        f.home_team.name.toLowerCase().includes(q) ||
        f.away_team.name.toLowerCase().includes(q) ||
        f.competition_name.toLowerCase().includes(q),
    )
  }, [all, search, searching])

  function cardFor(fixture: FixtureSummaryDto, status: 'live' | 'upcoming' | 'completed') {
    const { homeScore, awayScore } = fixtureScores(fixture.final_state)
    const href = status === 'completed' ? `/app/${sport.slug}/matches/${fixture.id}/review` : `/app/${sport.slug}/matches/${fixture.id}`
    return (
      <DiscoveryMatchCard
        key={fixture.id}
        competition={fixture.competition_name}
        competitionLogoUrl={fixture.competition_logo_url}
        status={status}
        kickoffLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
        venue={fixture.venue_name}
        homeTeam={fixture.home_team.name}
        awayTeam={fixture.away_team.name}
        homeScore={homeScore}
        awayScore={awayScore}
        homeLogoUrl={fixture.home_team.logo_url}
        awayLogoUrl={fixture.away_team.logo_url}
        sportDomain={domain}
        aiAvailable={status !== 'completed' && aiReady}
        following={watchlist.isFollowing('fixture', fixture.id)}
        onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
        href={href}
      />
    )
  }

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <MatchesHero sport={sport} onSportChange={setSport} search={search} onSearchChange={setSearch} backdropLogos={backdropLogos} />

      {isError && <ErrorState error={error} onRetry={refetch} />}

      {!isError && isLoading && <MissionSkeletonGrid count={6} />}

      {!isError && !isLoading && searching && (
        <MissionSection title={`Results for "${search.trim()}"`} subtitle={`${searchResults.length} match${searchResults.length === 1 ? '' : 'es'} matched`}>
          {searchResults.length === 0 ? (
            <MissionEmptyState icon={CalendarDays} title="No matches found" description={`Nothing in ${sport.label} matches "${search.trim()}" — try a different search.`} />
          ) : (
            <MatchGrid>
              {searchResults.map((f) =>
                cardFor(f, live.includes(f) ? 'live' : completed.includes(f) ? 'completed' : 'upcoming'),
              )}
            </MatchGrid>
          )}
        </MissionSection>
      )}

      {!isError && !isLoading && !searching && (
        <>
          {live.length > 0 && (
            <MissionSection title="Live" subtitle="On right now" icon={<Radio className="size-4" aria-hidden="true" />} domain={domain}>
              <MatchGrid>{live.map((f) => cardFor(f, 'live'))}</MatchGrid>
            </MissionSection>
          )}

          <MissionSection title="Upcoming" subtitle={`${sport.label} fixtures TitanIQ is tracking`} icon={<CalendarDays className="size-4" aria-hidden="true" />}>
            {upcoming.length === 0 ? (
              <MissionEmptyState icon={CalendarDays} title="No upcoming matches" description={`No ${sport.label} fixtures are scheduled yet.`} />
            ) : (
              <MatchGrid>{upcoming.slice(0, 12).map((f) => cardFor(f, 'upcoming'))}</MatchGrid>
            )}
          </MissionSection>

          {completed.length > 0 && (
            <MissionSection title="Recently Completed" subtitle="Final results" icon={<CheckCircle2 className="size-4" aria-hidden="true" />}>
              <MatchGrid>{completed.slice(0, 6).map((f) => cardFor(f, 'completed'))}</MatchGrid>
            </MissionSection>
          )}
        </>
      )}
    </div>
  )
}
