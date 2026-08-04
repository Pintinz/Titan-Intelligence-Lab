import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Radio, Star, Trophy } from 'lucide-react'
import { sportsApi, SPORT_OPTIONS, type SportCode } from '@/lib/api/sports'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { marketsApi } from '@/lib/api/markets'
import { fixtureScores } from '@/lib/sports-status'
import { cn } from '@/lib/cn'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import type { DomainKey } from '@/components/infinity/primitives/badge'

type SecondaryFilter = 'all' | 'following' | 'important'

const SECONDARY_FILTERS: Array<{ key: SecondaryFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'following', label: 'Following' },
  // "High importance" reads off Competition.tier (real data — top-flight leagues are tier 1),
  // not a fabricated importance score.
  { key: 'important', label: 'High importance' },
]

/** Cross-sport "what's live right now" — filters server-side on `status=live` per sport rather
 * than fetching a general fixture list and deriving live-ness client-side (the previous
 * approach), so this page only ever holds fixtures that are actually in progress. */
export default function LivePage() {
  const watchlist = useWatchlist()
  const [sportFilter, setSportFilter] = useState<SportCode | 'all'>('all')
  const [secondaryFilter, setSecondaryFilter] = useState<SecondaryFilter>('all')

  const activeSports = sportFilter === 'all' ? SPORT_SLUGS : SPORT_SLUGS.filter((s) => s.code === sportFilter)

  const fixtureQueries = useQueries({
    queries: activeSports.map((sport) => ({
      queryKey: ['sports', sport.code, 'fixtures', 'live-page', 'live'],
      queryFn: () => sportsApi.listFixturesPaged(sport.code, { status: 'live', limit: 50 }),
      refetchInterval: 30_000,
    })),
  })

  const marketQueries = useQueries({
    queries: activeSports.map((sport) => ({
      queryKey: ['markets', sport.code, 'production'],
      queryFn: () => marketsApi.list({ sport_code: sport.code, status: 'production' }),
      staleTime: 5 * 60 * 1000,
    })),
  })
  const aiAvailableBySport = new Set(
    activeSports.filter((_, i) => (marketQueries[i].data?.length ?? 0) > 0).map((s) => s.code),
  )

  const isPending = fixtureQueries.some((q) => q.isPending)
  const isError = fixtureQueries.every((q) => q.isError)
  const firstError = fixtureQueries.find((q) => q.isError)?.error

  const allLive = activeSports.flatMap((sport, i) => {
    const items = fixtureQueries[i].data?.items ?? []
    return items.map((fixture) => ({ fixture, sport }))
  })

  const liveFixtures = useMemo(() => {
    if (secondaryFilter === 'following') {
      return allLive.filter(({ fixture }) => watchlist.isFollowing('fixture', fixture.id))
    }
    if (secondaryFilter === 'important') {
      return allLive.filter(({ fixture }) => (fixture.competition_tier ?? 99) <= 1)
    }
    return allLive
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allLive, secondaryFilter, watchlist.data])

  return (
    <div className="space-y-6">
      <div>
        <InfinityLabel tone="var(--infinity-live)">Live</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          Every live match, across every sport
        </h2>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          <FilterChip active={sportFilter === 'all'} onClick={() => setSportFilter('all')}>
            All sports
          </FilterChip>
          {SPORT_OPTIONS.map((opt) => (
            <FilterChip key={opt.code} active={sportFilter === opt.code} onClick={() => setSportFilter(opt.code)}>
              {opt.label}
            </FilterChip>
          ))}
        </div>
        <div className="flex gap-1.5">
          {SECONDARY_FILTERS.map((f) => (
            <FilterChip key={f.key} active={secondaryFilter === f.key} onClick={() => setSecondaryFilter(f.key)} subtle>
              {f.key === 'following' && <Star className="size-3" aria-hidden="true" />}
              {f.key === 'important' && <Trophy className="size-3" aria-hidden="true" />}
              {f.label}
            </FilterChip>
          ))}
        </div>
      </div>

      {isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-40" />
          ))}
        </div>
      )}

      {!isPending && isError && <ErrorState error={firstError} onRetry={() => fixtureQueries.forEach((q) => void q.refetch())} />}

      {!isPending && !isError && liveFixtures.length === 0 && (
        <InfinityEmptyState
          icon={Radio}
          title="No live matches at the moment"
          description="Upcoming matches begin soon — check back shortly or browse the full schedule."
        />
      )}

      {liveFixtures.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {liveFixtures.map(({ fixture, sport }) => {
            const { homeScore, awayScore } = fixtureScores(fixture.final_state)
            return (
              <InfinityMatchCard
                key={fixture.id}
                sport={sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>}
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
                aiAvailable={aiAvailableBySport.has(sport.code)}
                following={watchlist.isFollowing('fixture', fixture.id)}
                onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
                href={`/app/${sport.slug}/matches/${fixture.id}`}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

function FilterChip({
  active,
  onClick,
  subtle,
  children,
}: {
  active: boolean
  onClick: () => void
  subtle?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 rounded-infinity-full border px-3 py-1.5 font-infinity-body text-[12px] font-medium transition-colors',
        active
          ? subtle
            ? 'border-infinity-border-strong bg-infinity-ground-2 text-infinity-text-primary'
            : 'border-infinity-live bg-infinity-live-muted text-infinity-live'
          : 'border-infinity-border-hairline text-infinity-text-secondary hover:border-infinity-border-default hover:text-infinity-text-primary',
      )}
    >
      {children}
    </button>
  )
}
