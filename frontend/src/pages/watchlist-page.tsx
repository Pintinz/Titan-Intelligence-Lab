import { useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { Plus, Users, Trophy, CircleDot, Sparkles, Star } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { marketsApi } from '@/lib/api/markets'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { ErrorState } from '@/components/ui/error-state'
import { CDButton } from '@/components/command-deck/primitives/button'
import { sportDomainFor, type DomainKey } from '@/components/command-deck/primitives/domain'
import { MissionSection, MissionEmptyState, MissionSkeletonGrid } from '@/components/command-deck/mission-control/mission-section'
import { WatchlistMatchCard } from '@/components/command-deck/watchlist/watchlist-match-card'
import { WatchlistTeamCard } from '@/components/command-deck/watchlist/watchlist-team-card'
import { WatchlistCompetitionCard } from '@/components/command-deck/watchlist/watchlist-competition-card'
import { WatchlistPredictionRow } from '@/components/command-deck/watchlist/watchlist-prediction-row'
import { AddToWatchlistDialog } from '@/components/command-deck/watchlist/add-to-watchlist-dialog'
import { dedupeByFixture } from '@/lib/predictions/dedupe-by-fixture'
import { deriveForm } from '@/lib/watchlist/form'
import { fixtureCardStatus, fixtureScores } from '@/lib/sports-status'
import type { WatchlistEntryDto, FixtureSummaryDto, PredictionPickDto } from '@/lib/api/types'

type SportDomain = Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

function sportSlugFor(sportCode: string | null | undefined): string {
  return (SPORT_SLUGS.find((s) => s.code === sportCode)?.slug ?? 'football').replace('_', '-')
}

function domainForSportCode(sportCode: string | null | undefined): SportDomain {
  return sportDomainFor(sportSlugFor(sportCode)) ?? 'football'
}

export default function WatchlistPage() {
  const watchlist = useWatchlist()
  const entries = watchlist.data ?? []
  const [addOpen, setAddOpen] = useState(false)

  const fixtureEntries = entries.filter((e) => e.entity_type === 'fixture')
  const teamEntries = entries.filter((e) => e.entity_type === 'team')
  const competitionEntries = entries.filter((e) => e.entity_type === 'competition')
  const predictionEntries = entries.filter((e) => e.entity_type === 'prediction')

  // -- Matches: fixture details + one bounded top-pick lookup shared by every match card --------
  const fixtureQueries = useQueries({
    queries: fixtureEntries.map((e) => ({
      queryKey: ['sports', 'fixture', e.entity_ref],
      queryFn: () => sportsApi.getFixture(e.entity_ref),
    })),
  })
  const picksQuery = useQuery({
    queryKey: ['predictions', 'picks', 'watchlist-top-picks'],
    queryFn: () => predictionsApi.picks({ limit: 200 }),
    enabled: fixtureEntries.length > 0,
  })
  const topPickByFixture = useMemo(() => {
    const map = new Map<string, PredictionPickDto>()
    for (const pick of dedupeByFixture(picksQuery.data ?? [])) map.set(pick.subject_ref, pick)
    return map
  }, [picksQuery.data])

  // -- Teams: identity + next match + recent form -----------------------------------------------
  const teamDetailQueries = useQueries({
    queries: teamEntries.map((e) => ({ queryKey: ['sports', 'teams', e.entity_ref], queryFn: () => sportsApi.getTeam(e.entity_ref) })),
  })
  const teamNextQueries = useQueries({
    queries: teamEntries.map((e) => ({
      queryKey: ['sports', 'team-fixtures', e.entity_ref, 'upcoming', 1],
      queryFn: () => sportsApi.teamFixtures(e.entity_ref, 1, 'upcoming'),
    })),
  })
  const teamFormQueries = useQueries({
    queries: teamEntries.map((e) => ({
      queryKey: ['sports', 'team-fixtures', e.entity_ref, 'recent', 5],
      queryFn: () => sportsApi.teamFixtures(e.entity_ref, 5, 'recent'),
    })),
  })

  // -- Competitions: identity + next fixtures ------------------------------------------------------
  const competitionDetailQueries = useQueries({
    queries: competitionEntries.map((e) => ({
      queryKey: ['sports', 'competitions', e.entity_ref],
      queryFn: () => sportsApi.getCompetition(e.entity_ref),
    })),
  })
  const competitionFixturesQueries = useQueries({
    queries: competitionEntries.map((e) => ({
      queryKey: ['sports', 'competitions', e.entity_ref, 'fixtures', 'watchlist'],
      queryFn: () => sportsApi.competitionFixtures(e.entity_ref, 20),
    })),
  })

  const isPending =
    watchlist.isPending ||
    fixtureQueries.some((q) => q.isPending) ||
    teamDetailQueries.some((q) => q.isPending) ||
    competitionDetailQueries.some((q) => q.isPending)

  // -- Next event: earliest real upcoming kickoff across everything already fetched above --------
  const nextEvent = useMemo(() => {
    const candidates: FixtureSummaryDto[] = [
      ...fixtureQueries.map((q) => q.data).filter((f): f is FixtureSummaryDto => !!f && fixtureCardStatus(f.status) !== 'completed'),
      ...teamNextQueries.flatMap((q) => q.data ?? []),
      ...competitionFixturesQueries.flatMap((q) => (q.data ?? []).filter((f) => f.status.toLowerCase() === 'scheduled')),
    ]
    if (candidates.length === 0) return null
    return candidates.reduce((earliest, f) => (new Date(f.scheduled_at) < new Date(earliest.scheduled_at) ? f : earliest))
  }, [fixtureQueries, teamNextQueries, competitionFixturesQueries])

  if (watchlist.isError) {
    return <ErrorState error={watchlist.error} onRetry={() => void watchlist.refetch()} />
  }

  const allEmpty = watchlist.data && entries.length === 0

  return (
    <div className="command-deck space-y-8 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]" style={{ color: 'var(--cd-accent)' }}>
            Watchlist
          </p>
          <h2 className="mt-1 font-[var(--cd-font-display)] text-[26px] font-semibold tracking-[-0.01em] sm:text-[30px]" style={{ color: 'var(--cd-text-primary)' }}>
            Your Intelligence Watchlist
          </h2>
          <p className="mt-1 max-w-xl font-[var(--cd-font-body)] text-[13.5px]" style={{ color: 'var(--cd-text-muted)' }}>
            Track matches, teams, competitions, and AI predictions that matter to you.
          </p>
        </div>
        <CDButton variant="primary" onClick={() => setAddOpen(true)} icon={<Plus className="size-4" aria-hidden="true" />}>
          Add to Watchlist
        </CDButton>
      </div>

      {!isPending && !allEmpty && (
        <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1 sm:grid sm:grid-cols-4 sm:overflow-visible">
          <KpiTile label="Matches" value={fixtureEntries.length} />
          <KpiTile label="Teams" value={teamEntries.length} />
          <KpiTile label="Competitions" value={competitionEntries.length} />
          <KpiTile label="Predictions" value={predictionEntries.length} />
          {nextEvent && (
            <KpiTile
              label="Next event"
              value={`${nextEvent.home_team.short_name || nextEvent.home_team.name} vs ${nextEvent.away_team.short_name || nextEvent.away_team.name}`}
              sub={new Date(nextEvent.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              wide
            />
          )}
        </div>
      )}

      {isPending && <MissionSkeletonGrid count={3} />}

      {allEmpty && (
        <MissionEmptyState
          icon={Star}
          title="Watchlist clear"
          description="Your watchlist is clear. Follow a team, competition, or match and TitanIQ will keep its intelligence within reach."
          actionLabel="Explore matches"
          actionHref="/app/football/matches"
        />
      )}

      {!isPending && !allEmpty && (
        <>
          <MissionSection title={`Matches · ${fixtureEntries.length}`} icon={<CircleDot className="size-4" aria-hidden="true" />} domain="predictions">
            {fixtureEntries.length === 0 ? (
              <MissionEmptyState
                title="No matches followed yet"
                description="Follow a match to keep its schedule and AI intelligence within reach."
                actionLabel="Explore matches"
                actionHref="/app/football/matches"
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {fixtureEntries.map((entry, i) => {
                  const query = fixtureQueries[i]
                  if (query.isPending) return <div key={entry.id} className="h-56 animate-pulse rounded-[var(--cd-radius-xl)] motion-reduce:animate-none" style={{ background: 'var(--cd-card-surface)' }} />
                  if (query.isError || !query.data) return <UnresolvedEntry key={entry.id} onUnfollow={() => watchlist.toggle('fixture', entry.entity_ref)} />
                  const fixture = query.data
                  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
                  const sportSlug = sportSlugFor(fixture.sport_code)
                  return (
                    <WatchlistMatchCard
                      key={entry.id}
                      competition={fixture.competition_name}
                      competitionLogoUrl={fixture.competition_logo_url}
                      status={fixtureCardStatus(fixture.status)}
                      kickoffLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                      venue={fixture.venue_name}
                      homeTeam={fixture.home_team.name}
                      awayTeam={fixture.away_team.name}
                      homeScore={homeScore}
                      awayScore={awayScore}
                      homeLogoUrl={fixture.home_team.logo_url}
                      awayLogoUrl={fixture.away_team.logo_url}
                      sportDomain={domainForSportCode(fixture.sport_code)}
                      topPick={topPickByFixture.get(fixture.id) ?? null}
                      following
                      onToggleFollow={() => watchlist.toggle('fixture', entry.entity_ref)}
                      href={`/app/${sportSlug}/matches/${fixture.id}`}
                    />
                  )
                })}
              </div>
            )}
          </MissionSection>

          <MissionSection title={`Predictions · ${predictionEntries.length}`} icon={<Sparkles className="size-4" aria-hidden="true" />} domain="predictions">
            {predictionEntries.length === 0 ? (
              <MissionEmptyState
                title="No predictions followed yet"
                description="Follow a prediction from Match Intelligence to monitor it here."
                actionLabel="Explore AI Picks"
                actionHref="/app/picks"
              />
            ) : (
              <div className="space-y-2">
                {predictionEntries.map((entry) => (
                  <PredictionFeedItem key={entry.id} entry={entry} onUnfollow={() => watchlist.toggle('prediction', entry.entity_ref)} />
                ))}
              </div>
            )}
          </MissionSection>

          <MissionSection title={`Teams · ${teamEntries.length}`} icon={<Users className="size-4" aria-hidden="true" />}>
            {teamEntries.length === 0 ? (
              <MissionEmptyState title="No teams followed yet" actionLabel="Explore teams" actionHref="/app/teams" description="Follow a team to monitor its schedule and form here." />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {teamEntries.map((entry, i) => {
                  const detail = teamDetailQueries[i]
                  if (detail.isPending) return <div key={entry.id} className="h-56 animate-pulse rounded-[var(--cd-radius-md)] motion-reduce:animate-none" style={{ background: 'var(--cd-surface-1)' }} />
                  if (detail.isError || !detail.data) return <UnresolvedEntry key={entry.id} onUnfollow={() => watchlist.toggle('team', entry.entity_ref)} />
                  const team = detail.data
                  const nextMatch = teamNextQueries[i].data?.[0] ?? null
                  const form = deriveForm(teamFormQueries[i].data ?? [], team.id).slice(-5)
                  const sportSlug = sportSlugFor(team.sport_code)
                  return (
                    <WatchlistTeamCard
                      key={entry.id}
                      team={team}
                      href={`/app/${sportSlug}/teams/${team.id}`}
                      sportDomain={domainForSportCode(team.sport_code)}
                      nextMatch={nextMatch}
                      form={form}
                      following
                      onToggleFollow={() => watchlist.toggle('team', entry.entity_ref)}
                    />
                  )
                })}
              </div>
            )}
          </MissionSection>

          <MissionSection title={`Competitions · ${competitionEntries.length}`} icon={<Trophy className="size-4" aria-hidden="true" />}>
            {competitionEntries.length === 0 ? (
              <MissionEmptyState
                title="No competitions followed yet"
                actionLabel="Explore competitions"
                actionHref="/app/competitions"
                description="Follow a competition to monitor its fixtures here."
              />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {competitionEntries.map((entry, i) => {
                  const detail = competitionDetailQueries[i]
                  if (detail.isPending) return <div key={entry.id} className="h-64 animate-pulse rounded-[var(--cd-radius-2xl)] motion-reduce:animate-none" style={{ background: 'var(--cd-card-surface)' }} />
                  if (detail.isError || !detail.data) return <UnresolvedEntry key={entry.id} onUnfollow={() => watchlist.toggle('competition', entry.entity_ref)} />
                  const competition = detail.data
                  const nextFixtures = (competitionFixturesQueries[i].data ?? [])
                    .filter((f) => f.status.toLowerCase() === 'scheduled')
                    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
                    .slice(0, 3)
                  const sportSlug = sportSlugFor(competition.sport_code)
                  return (
                    <WatchlistCompetitionCard
                      key={entry.id}
                      competition={competition}
                      href={`/app/${sportSlug}/competitions/${competition.id}`}
                      sportDomain={domainForSportCode(competition.sport_code)}
                      nextFixtures={nextFixtures}
                      following
                      onToggleFollow={() => watchlist.toggle('competition', entry.entity_ref)}
                    />
                  )
                })}
              </div>
            )}
          </MissionSection>
        </>
      )}

      <AddToWatchlistDialog open={addOpen} onOpenChange={setAddOpen} />
    </div>
  )
}

function KpiTile({ label, value, sub, wide }: { label: string; value: string | number; sub?: string; wide?: boolean }) {
  return (
    <div
      className={`shrink-0 rounded-[var(--cd-radius-lg)] px-4 py-3 ${wide ? 'min-w-[10rem] flex-1' : 'min-w-[6.5rem]'}`}
      style={{ backgroundColor: 'var(--cd-surface-1)', border: '1px solid var(--cd-border-default)' }}
    >
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label}
      </p>
      <p className={`mt-1 truncate font-[var(--cd-font-tabular)] font-semibold tabular-nums ${wide ? 'text-[14px]' : 'text-2xl'}`} style={{ color: 'var(--cd-text-primary)' }}>
        {value}
      </p>
      {sub && (
        <p className="mt-0.5 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          {sub}
        </p>
      )}
    </div>
  )
}

function UnresolvedEntry({ onUnfollow }: { onUnfollow: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[var(--cd-radius-md)] border border-dashed p-4" style={{ borderColor: 'var(--cd-border-default)' }}>
      <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
        No longer available.
      </p>
      <button type="button" onClick={onUnfollow} className="font-[var(--cd-font-body)] text-[12px] font-medium" style={{ color: 'var(--cd-accent)' }}>
        Remove
      </button>
    </div>
  )
}

/** A followed prediction resolves subject_ref -> fixture (team names, sport) and market_id ->
 * market name via that sport's already-cached production markets list — the same two-hop
 * resolution the rest of Command Deck uses, kept local since only this compact feed row needs it. */
function PredictionFeedItem({ entry, onUnfollow }: { entry: WatchlistEntryDto; onUnfollow: () => void }) {
  const predictionQuery = useQuery({ queryKey: ['predictions', entry.entity_ref], queryFn: () => predictionsApi.get(entry.entity_ref) })
  const prediction = predictionQuery.data

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', prediction?.subject_ref],
    queryFn: () => sportsApi.getFixture(prediction!.subject_ref),
    enabled: !!prediction,
  })
  const fixture = fixtureQuery.data

  const marketsQuery = useQuery({
    queryKey: ['markets', fixture?.sport_code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: fixture!.sport_code!, status: 'production' }),
    enabled: !!fixture?.sport_code,
  })
  const market = marketsQuery.data?.find((m) => m.id === prediction?.market_id)

  if (predictionQuery.isPending) {
    return <div className="h-16 animate-pulse rounded-[var(--cd-radius-md)] motion-reduce:animate-none" style={{ background: 'var(--cd-surface-1)' }} />
  }
  if (predictionQuery.isError || !prediction) {
    return <UnresolvedEntry onUnfollow={onUnfollow} />
  }

  const evidenceCount = prediction.explanation
    ? prediction.explanation.top_positive_features.length + prediction.explanation.top_negative_features.length
    : null
  const sportSlug = sportSlugFor(fixture?.sport_code)
  const href = fixture ? `/app/${sportSlug}/matches/${fixture.id}` : '#'

  return (
    <WatchlistPredictionRow
      fixtureLabel={fixture ? `${fixture.home_team.name} vs ${fixture.away_team.name}` : null}
      marketName={market?.name ?? null}
      value={prediction.value}
      homeTeam={fixture ? { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url } : undefined}
      awayTeam={fixture ? { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url } : undefined}
      confidence={prediction.confidence.composite}
      evidenceCount={evidenceCount}
      generatedAt={prediction.generated_at}
      href={href}
      following
      onToggleFollow={onUnfollow}
    />
  )
}
