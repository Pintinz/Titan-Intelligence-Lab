import { Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ChevronRight } from 'lucide-react'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import { DiscoveryMatchCard } from './discovery-match-card'
import { MatchSnapshotCard } from '../match-snapshot-card'
import type { MatchesScope } from '@/pages/sports/match-list-view-all-page'

interface DateRange {
  from: string
  to: string
}

/**
 * DiscoverySection — one real fixture window (Today / Upcoming / Completed), Command Deck's
 * card grammar applied to the same section shape `match-list-page.tsx` already used. An empty
 * window states plainly that AI is monitoring, not a fabricated reassurance.
 */
export function DiscoverySection({
  sportSlug,
  sportCode,
  scope,
  title,
  range,
  competitionId,
  aiAvailable,
  followingOnly,
  limit = 6,
}: {
  sportSlug: string
  sportCode: SportCode
  scope: MatchesScope
  title: string
  range: DateRange | null
  competitionId: string
  aiAvailable: boolean
  followingOnly: boolean
  limit?: number
}) {
  const watchlist = useWatchlist()
  const query = useQuery({
    queryKey: ['sports', sportCode, 'fixtures', 'discovery-section', scope, competitionId],
    queryFn: () =>
      sportsApi.listFixturesPaged(sportCode, {
        ...(range ? { date_from: range.from, date_to: range.to } : {}),
        ...(scope === 'completed' ? { status: 'completed' } : {}),
        competition_id: competitionId || undefined,
        limit,
      }),
  })

  const items = (query.data?.items ?? []).filter((f) => !followingOnly || watchlist.isFollowing('fixture', f.id))

  // Completed matches get the same AI Match Snapshot card design as Recent Form (real stat
  // chips + a deterministic snapshot sentence, both from `buildMatchSnapshot`) instead of the
  // plain fixture-scan card — a completed match has a real result and real statistics to show,
  // which is exactly what that card design was built for. Narrated from the home side's
  // perspective, a fixed, consistent choice for a list not scoped to any one team (matches its
  // team-scoped usage on match-detail-page.tsx's Recent Form, which narrates from whichever team
  // that column belongs to).
  const isCompleted = scope === 'completed'
  const statsQueries = useQueries({
    queries: isCompleted
      ? items.map((fixture) => ({
          queryKey: ['sports', 'fixture-statistics', fixture.id],
          queryFn: () => sportsApi.fixtureStatistics(fixture.id),
          staleTime: 5 * 60 * 1000,
        }))
      : [],
  })

  return (
    <section id={scope} className="scroll-mt-24">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {title}
        </h3>
        <Link
          to={`/app/${sportSlug}/matches/${scope}`}
          className="inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
          style={{ color: 'var(--cd-accent)' }}
        >
          View all <ChevronRight className="size-3.5" aria-hidden="true" />
        </Link>
      </div>

      {query.isPending && (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-44 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ))}
        </div>
      )}

      {!query.isPending && items.length === 0 && (
        <div className="rounded-[var(--cd-radius-lg)] border border-dashed px-4 py-6 text-center" style={{ borderColor: 'var(--cd-border-default)' }}>
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
            {followingOnly
              ? 'None of your followed matches fall in this window.'
              : `No fixtures under TitanIQ coverage in this window yet.`}
          </p>
          {!followingOnly && (
            <p className="mt-1 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
              The AI is continuously monitoring supported competitions and will surface new matches automatically.
            </p>
          )}
        </div>
      )}

      {items.length > 0 && (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((fixture, i) => {
            const { homeScore, awayScore } = fixtureScores(fixture.final_state)
            const status = fixtureCardStatus(fixture.status)
            const href = status === 'completed' ? `/app/${sportSlug}/matches/${fixture.id}/review` : `/app/${sportSlug}/matches/${fixture.id}`

            if (isCompleted && homeScore !== undefined && awayScore !== undefined) {
              const statsRows = statsQueries[i]?.data
              return (
                <MatchSnapshotCard
                  key={fixture.id}
                  competition={fixture.competition_name}
                  competitionLogoUrl={fixture.competition_logo_url}
                  dateLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                  teamName={fixture.home_team.name}
                  teamLogoUrl={fixture.home_team.logo_url}
                  opponentName={fixture.away_team.name}
                  opponentLogoUrl={fixture.away_team.logo_url}
                  perspectiveIsHome
                  homeScore={homeScore}
                  awayScore={awayScore}
                  perspectiveStats={statsRows?.find((row) => row.team_id === fixture.home_team.id)?.stats}
                  opponentStats={statsRows?.find((row) => row.team_id === fixture.away_team.id)?.stats}
                  statsLoading={statsQueries[i]?.isPending}
                  href={href}
                />
              )
            }

            return (
              <DiscoveryMatchCard
                key={fixture.id}
                competition={fixture.competition_name}
                competitionLogoUrl={fixture.competition_logo_url}
                status={status}
                kickoffLabel={
                  status === 'upcoming'
                    ? new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                    : status === 'completed'
                      ? 'Full time'
                      : undefined
                }
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
                href={href}
              />
            )
          })}
        </div>
      )}
    </section>
  )
}
