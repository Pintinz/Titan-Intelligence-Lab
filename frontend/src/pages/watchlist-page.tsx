import type { ReactNode } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Star, CircleDot, Users, Trophy, Sparkles } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { ErrorState } from '@/components/ui/error-state'
import { InfinityLabel } from '@/components/infinity/primitives/panel'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { InfinityConfidenceRing } from '@/components/infinity/charts/confidence-ring'
import { InfinityMatchCard } from '@/components/infinity/cards/match-card'
import { InfinityTeamCard } from '@/components/infinity/cards/team-card'
import { InfinityCompetitionCard } from '@/components/infinity/cards/competition-card'
import { InfinityFollowButton } from '@/components/infinity/primitives/follow-button'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import type { WatchlistEntryDto } from '@/lib/api/types'
import type { DomainKey } from '@/components/infinity/primitives/badge'

function sportSlugFor(sportCode: string): 'football' | 'basketball' | 'baseball' | 'table-tennis' | null {
  return (SPORT_SLUGS.find((s) => s.code === sportCode)?.slug as ReturnType<typeof sportSlugFor>) ?? null
}

export default function WatchlistPage() {
  const watchlist = useWatchlist()
  const entries = watchlist.data ?? []

  const fixtures = entries.filter((e) => e.entity_type === 'fixture')
  const teams = entries.filter((e) => e.entity_type === 'team')
  const competitions = entries.filter((e) => e.entity_type === 'competition')
  const predictions = entries.filter((e) => e.entity_type === 'prediction')

  return (
    <div className="space-y-8">
      <div>
        <InfinityLabel tone="var(--infinity-signal)">Watchlist</InfinityLabel>
        <h2 className="mt-1 font-infinity-display text-lg font-semibold text-infinity-text-primary">
          Everything you're following
        </h2>
      </div>

      {watchlist.isPending && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <InfinitySkeleton key={i} className="h-24" />
          ))}
        </div>
      )}

      {watchlist.isError && <ErrorState error={watchlist.error} onRetry={() => void watchlist.refetch()} />}

      {watchlist.data && entries.length === 0 && (
        <InfinityEmptyState
          icon={Star}
          title="Nothing followed yet"
          description="Follow a match, team, or competition from its card to track it here."
        />
      )}

      {fixtures.length > 0 && (
        <WatchlistSection
          icon={CircleDot}
          title="Matches"
          entries={fixtures}
          render={(entry) => <FixtureEntry key={entry.id} entry={entry} onUnfollow={() => watchlist.toggle('fixture', entry.entity_ref)} />}
        />
      )}

      {teams.length > 0 && (
        <WatchlistSection
          icon={Users}
          title="Teams"
          entries={teams}
          render={(entry) => <TeamEntry key={entry.id} entry={entry} onUnfollow={() => watchlist.toggle('team', entry.entity_ref)} />}
        />
      )}

      {competitions.length > 0 && (
        <WatchlistSection
          icon={Trophy}
          title="Competitions"
          entries={competitions}
          render={(entry) => (
            <CompetitionEntry key={entry.id} entry={entry} onUnfollow={() => watchlist.toggle('competition', entry.entity_ref)} />
          )}
        />
      )}

      {predictions.length > 0 && (
        <WatchlistSection
          icon={Sparkles}
          title="Predictions"
          entries={predictions}
          render={(entry) => (
            <PredictionEntry key={entry.id} entry={entry} onUnfollow={() => watchlist.toggle('prediction', entry.entity_ref)} />
          )}
        />
      )}
    </div>
  )
}

function WatchlistSection({
  icon: Icon,
  title,
  entries,
  render,
}: {
  icon: typeof Star
  title: string
  entries: WatchlistEntryDto[]
  render: (entry: WatchlistEntryDto) => ReactNode
}) {
  return (
    <div>
      <div className="flex items-center gap-2">
        <Icon className="size-3.5 text-infinity-text-muted" aria-hidden="true" />
        <InfinityLabel>
          {title} ({entries.length})
        </InfinityLabel>
      </div>
      <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{entries.map(render)}</div>
    </div>
  )
}

function FixtureEntry({ entry, onUnfollow }: { entry: WatchlistEntryDto; onUnfollow: () => void }) {
  const query = useQueries({
    queries: [{ queryKey: ['sports', 'fixtures', entry.entity_ref], queryFn: () => sportsApi.getFixture(entry.entity_ref) }],
  })[0]

  if (query.isPending) return <InfinitySkeleton className="h-24" />
  if (query.isError || !query.data) return <UnresolvedEntry onUnfollow={onUnfollow} />

  const fixture = query.data
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const sportSlug = (fixture.sport_code ?? 'football').replace('_', '-') as
    Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  return (
    <InfinityMatchCard
      sport={sportSlug}
      competition={fixture.competition_name}
      competitionLogoUrl={fixture.competition_logo_url}
      status={fixtureCardStatus(fixture.status)}
      kickoff={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
      venue={fixture.venue_name}
      homeTeam={fixture.home_team?.name ?? 'TBD'}
      awayTeam={fixture.away_team?.name ?? 'TBD'}
      homeScore={homeScore}
      awayScore={awayScore}
      homeLogoUrl={fixture.home_team?.logo_url}
      awayLogoUrl={fixture.away_team?.logo_url}
      following
      onToggleFollow={onUnfollow}
      href={`/app/${sportSlug}/matches/${fixture.id}`}
    />
  )
}

function TeamEntry({ entry, onUnfollow }: { entry: WatchlistEntryDto; onUnfollow: () => void }) {
  const query = useQueries({
    queries: [{ queryKey: ['sports', 'teams', entry.entity_ref], queryFn: () => sportsApi.getTeam(entry.entity_ref) }],
  })[0]

  if (query.isPending) return <InfinitySkeleton className="h-20" />
  if (query.isError || !query.data) return <UnresolvedEntry onUnfollow={onUnfollow} />

  const team = query.data
  const slug = sportSlugFor(team.sport_code) ?? 'football'
  return (
    <InfinityTeamCard
      name={team.name}
      domain={slug}
      country={team.country}
      venueName={team.venue_name}
      following
      onToggleFollow={onUnfollow}
    />
  )
}

function CompetitionEntry({ entry, onUnfollow }: { entry: WatchlistEntryDto; onUnfollow: () => void }) {
  const query = useQueries({
    queries: [
      { queryKey: ['sports', 'competitions', entry.entity_ref], queryFn: () => sportsApi.getCompetition(entry.entity_ref) },
    ],
  })[0]

  if (query.isPending) return <InfinitySkeleton className="h-20" />
  if (query.isError || !query.data) return <UnresolvedEntry onUnfollow={onUnfollow} />

  const competition = query.data
  const slug = sportSlugFor(competition.sport_code) ?? 'football'
  return (
    <InfinityCompetitionCard
      name={competition.name}
      domain={slug}
      type={competition.type}
      country={competition.country}
      tier={competition.tier}
      logoUrl={competition.logo_url}
      following
      onToggleFollow={onUnfollow}
    />
  )
}

function PredictionEntry({ entry, onUnfollow }: { entry: WatchlistEntryDto; onUnfollow: () => void }) {
  const query = useQueries({
    queries: [{ queryKey: ['predictions', entry.entity_ref], queryFn: () => predictionsApi.get(entry.entity_ref) }],
  })[0]

  if (query.isPending) return <InfinitySkeleton className="h-20" />
  if (query.isError || !query.data) return <UnresolvedEntry onUnfollow={onUnfollow} />

  const prediction = query.data
  return (
    <div className="flex items-center justify-between gap-3 rounded-infinity-md border border-infinity-border-hairline bg-infinity-ground-1 p-4">
      <div className="min-w-0">
        <InfinityLabel tone="var(--infinity-domain-predictions)">{prediction.subject_ref}</InfinityLabel>
        <p className="mt-1 truncate font-infinity-telemetry text-[15px] font-semibold text-infinity-text-primary">
          {String(prediction.value)}
        </p>
        <p className="mt-1 font-infinity-mono text-[11px] text-infinity-text-muted">
          {(prediction.probability * 100).toFixed(1)}% probability
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <InfinityConfidenceRing value={prediction.confidence.composite} size={44} />
        <InfinityFollowButton following onToggle={onUnfollow} label={String(prediction.value)} />
      </div>
    </div>
  )
}

function UnresolvedEntry({ onUnfollow }: { onUnfollow: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-infinity-md border border-dashed border-infinity-border-default p-4">
      <p className="font-infinity-body text-[12px] text-infinity-text-muted">No longer available.</p>
      <InfinityFollowButton following onToggle={onUnfollow} label="unavailable item" />
    </div>
  )
}
