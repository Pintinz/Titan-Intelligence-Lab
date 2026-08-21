import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useMutation, useQueries, useQuery } from '@tanstack/react-query'
import { ArrowLeft, HeartPulse, Radio } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { marketsApi } from '@/lib/api/markets'
import { predictionsApi } from '@/lib/api/predictions'
import { useSportParam } from '@/lib/hooks/use-sport'
import { useWatchlist } from '@/lib/hooks/use-watchlist'
import { useRealtimeInvalidate } from '@/lib/hooks/use-realtime-invalidate'
import { fixtureScores, countdownLabel } from '@/lib/sports-status'
import { ErrorState } from '@/components/ui/error-state'
import { type DomainKey } from '@/components/infinity/primitives/badge'
import { InfinitySkeleton } from '@/components/infinity/primitives/skeleton'
import { InfinityEmptyState } from '@/components/infinity/primitives/empty-state'
import { CommandDeckHero } from '@/components/command-deck/hero'
import { AIMatchSnapshot } from '@/components/command-deck/ai-snapshot'
import { PredictionLaboratory } from '@/components/command-deck/prediction-laboratory'
import { GeneratedIntelligencePanel } from '@/components/command-deck/generated-intelligence'
import { MatchSnapshotCard } from '@/components/command-deck/match-snapshot-card'
import type { FixtureSummaryDto, InjuryDto } from '@/lib/api/types'

function isLiveStatus(status: string) {
  return status.toLowerCase() === 'live' || status.toLowerCase() === 'in_play'
}

/** Football insight types beyond Match Winner that TitanIQ's market catalog doesn't have yet —
 * shown as an honest roadmap, never as a fake interactive option, so the selector communicates
 * "more is coming" without pretending a market exists that the backend can't actually generate. */
const UPCOMING_FOOTBALL_INSIGHTS = ['Goals', 'Both Teams to Score', 'Correct Score', 'Double Chance', 'Handicap', 'Corners', 'Cards']

export default function MatchDetailPage() {
  const sport = useSportParam()
  const { matchId } = useParams<{ matchId: string }>()
  const [selectedMarketKey, setSelectedMarketKey] = useState<string | null>(null)
  const watchlist = useWatchlist()

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', matchId],
    queryFn: () => sportsApi.getFixture(matchId!),
    enabled: !!matchId,
  })

  useRealtimeInvalidate('matches', [['sports', 'fixture', matchId]], matchId ? `fixture_id=eq.${matchId}` : undefined)

  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })

  useRealtimeInvalidate(
    'predictionMarkets',
    [['markets', sport?.code, 'production']],
    sport ? `sport_code=eq.${sport.code}` : undefined,
  )

  const generateIntelligence = useMutation({
    mutationFn: (marketKey: string) =>
      predictionsApi.generate({
        market_key: marketKey,
        entity_type: 'fixture',
        entity_id: matchId!,
        subject_ref: matchId!,
        include_football_explanation: sport?.code === 'football',
        include_contextual_review: true,
      }),
  })

  const fixture = fixtureQuery.data

  const homeFixturesQuery = useQuery({
    queryKey: ['sports', 'team-fixtures', fixture?.home_team?.id],
    queryFn: () => sportsApi.teamFixtures(fixture!.home_team.id, 5),
    enabled: !!fixture?.home_team,
  })
  const awayFixturesQuery = useQuery({
    queryKey: ['sports', 'team-fixtures', fixture?.away_team?.id],
    queryFn: () => sportsApi.teamFixtures(fixture!.away_team.id, 5),
    enabled: !!fixture?.away_team,
  })
  const homeInjuriesQuery = useQuery({
    queryKey: ['sports', 'team', fixture?.home_team?.id, 'injuries'],
    queryFn: () => sportsApi.teamInjuries(fixture!.home_team.id),
    enabled: !!fixture?.home_team,
  })
  const awayInjuriesQuery = useQuery({
    queryKey: ['sports', 'team', fixture?.away_team?.id, 'injuries'],
    queryFn: () => sportsApi.teamInjuries(fixture!.away_team.id),
    enabled: !!fixture?.away_team,
  })

  if (!sport) return null

  if (fixtureQuery.isPending) {
    return (
      <div className="space-y-4">
        <InfinitySkeleton className="h-8 w-64" />
        <InfinitySkeleton className="h-40" />
      </div>
    )
  }

  if (fixtureQuery.isError) {
    return <ErrorState error={fixtureQuery.error} onRetry={() => void fixtureQuery.refetch()} />
  }

  if (!fixture) return null

  // Some fixtures reference a team_id the backend can no longer resolve (e.g. after a team
  // merge) and serialize home_team/away_team as null despite the DTO's non-null type — show an
  // honest error rather than crashing on every downstream .name/.id/.logo_url access below.
  if (!fixture.home_team || !fixture.away_team) {
    return <ErrorState error={new Error('Team data is unavailable for this match.')} />
  }

  const markets = marketsQuery.data ?? []
  const domain = sport.slug as Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
  const live = isLiveStatus(fixture.status)
  const isCompleted = fixture.status.toLowerCase() === 'completed'
  const aiAvailable = markets.length > 0
  const countdown = !live && !isCompleted ? countdownLabel(fixture.scheduled_at) : null
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)

  function handleSelectMarket(marketKey: string) {
    setSelectedMarketKey(marketKey)
    generateIntelligence.reset()
  }

  const matchStatusLabel = live ? 'Live' : isCompleted ? 'Final' : countdown ?? fixture.status
  const matchStatusTone: 'live' | 'idle' | 'accent' = live ? 'live' : isCompleted ? 'idle' : 'accent'
  const upcomingInsights =
    domain === 'football'
      ? UPCOMING_FOOTBALL_INSIGHTS.filter((label) => !markets.some((market) => market.name.toLowerCase().includes(label.toLowerCase())))
      : []
  const selectedMarket = markets.find((m) => m.market_key === selectedMarketKey)

  return (
    <div className="max-w-7xl space-y-8">
      <Link
        to={`/app/${sport.slug}/matches`}
        className="inline-flex items-center gap-1 font-infinity-body text-[13px] text-infinity-text-secondary hover:text-infinity-text-primary"
      >
        <ArrowLeft className="size-3.5" /> Back to matches
      </Link>

      {/* Command Deck — Phase 1 scope: Hero, AI Match Snapshot, Prediction Laboratory, Generated
          Intelligence. A deliberate, disclosed visual-world seam: everything below (Recent Form,
          Match Coverage, Match Context) stays on Infinity in this pass. */}
      <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
        <CommandDeckHero
          competition={fixture.competition_name}
          aiAvailable={aiAvailable}
          live={live}
          statusLabel={matchStatusLabel}
          homeTeam={{ name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }}
          awayTeam={{ name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }}
          homeScore={homeScore}
          awayScore={awayScore}
          countdown={countdown ? `Kicks off in ${countdown}` : null}
          scheduledAt={fixture.scheduled_at}
          venueName={fixture.venue_name}
          following={watchlist.isFollowing('fixture', fixture.id)}
          onToggleFollow={() => watchlist.toggle('fixture', fixture.id)}
          matchId={fixture.id}
        />

        <AIMatchSnapshot
          intelligenceTypeCount={markets.length}
          matchStatusLabel={matchStatusLabel}
          matchStatusTone={matchStatusTone}
          aiReady={aiAvailable}
        />

        <div className="space-y-6">
          <div>
            {marketsQuery.isPending && (
              <div className="grid gap-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <InfinitySkeleton key={i} className="h-16" />
                ))}
              </div>
            )}
            {marketsQuery.isError && <ErrorState error={marketsQuery.error} onRetry={() => void marketsQuery.refetch()} />}
            {markets.length === 0 && !marketsQuery.isPending && !marketsQuery.isError && (
              <InfinityEmptyState
                icon={Radio}
                title="Intelligence isn't available for this sport yet"
                description={`TitanIQ hasn't finished building out AI intelligence for ${sport.label} — it's coming.`}
              />
            )}
            {markets.length > 0 && (
              <PredictionLaboratory
                markets={markets}
                selectedMarketKey={selectedMarketKey}
                onSelect={handleSelectMarket}
                onGenerate={() => generateIntelligence.mutate(selectedMarketKey!)}
                generating={generateIntelligence.isPending}
                hasGenerated={!!generateIntelligence.data}
              />
            )}
            {upcomingInsights.length > 0 && (
              <div className="mt-3">
                <p className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.08em]" style={{ color: 'var(--cd-text-muted)' }}>
                  More on the way
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {upcomingInsights.map((label) => (
                    <span
                      key={label}
                      className="rounded-full border px-2.5 py-1 font-[var(--cd-font-body)] text-[11px]"
                      style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-muted)' }}
                      title={`${label} intelligence isn't built yet`}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
          {/* Only mounted once "Generate Intelligence" has actually been clicked — stays out of
              the page entirely until then, per the approved brief, rather than sitting there as
              an idle placeholder above the fold. */}
          {(generateIntelligence.isPending || !!generateIntelligence.data || !!generateIntelligence.error) && (
            <GeneratedIntelligencePanel
              marketName={selectedMarket?.name ?? null}
              prediction={generateIntelligence.data}
              isGenerating={generateIntelligence.isPending}
              error={generateIntelligence.error}
              homeTeam={{ name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }}
              awayTeam={{ name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }}
            />
          )}
        </div>
      </div>

      <div className="space-y-8">
        {/* Recent form (home + away) — AI Match Snapshot cards, Command Deck world */}
        <div className="command-deck">
          <div className="mb-4 flex items-center gap-2">
            <Radio className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <p className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>Recent form</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <FormColumn
              teamId={fixture.home_team.id}
              teamName={fixture.home_team.name}
              label="Home form"
              sportSlug={sport.slug}
              query={homeFixturesQuery}
              excludeId={fixture.id}
            />
            <FormColumn
              teamId={fixture.away_team.id}
              teamName={fixture.away_team.name}
              label="Away form"
              sportSlug={sport.slug}
              query={awayFixturesQuery}
              excludeId={fixture.id}
            />
          </div>
        </div>

        {/* Team news (injuries) — both sides, real reported status only */}
        <div className="command-deck">
          <div className="mb-4 flex items-center gap-2">
            <HeartPulse className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <p className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>Team news</p>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <TeamNewsColumn teamName={fixture.home_team.name} query={homeInjuriesQuery} />
            <TeamNewsColumn teamName={fixture.away_team.name} query={awayInjuriesQuery} />
          </div>
        </div>
      </div>
    </div>
  )
}

function TeamNewsColumn({ teamName, query }: { teamName: string; query: { isPending: boolean; data: InjuryDto[] | undefined } }) {
  const injuries = query.data ?? []
  return (
    <div className="rounded-[var(--cd-radius-lg)] border p-4" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-1)' }}>
      <p className="mb-3 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {teamName}
      </p>
      {query.isPending && <InfinitySkeleton className="h-12" />}
      {!query.isPending && injuries.length === 0 && (
        <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          No reported injuries.
        </p>
      )}
      {!query.isPending && injuries.length > 0 && (
        <ul className="space-y-1.5">
          {injuries.slice(0, 6).map((injury) => (
            <li key={injury.id} className="flex items-center justify-between gap-2 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
              <span>{injury.player_name ?? 'Unknown player'}</span>
              <span style={{ color: 'var(--cd-danger)' }}>{injury.reason ?? injury.status}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function FormColumn({
  teamId,
  teamName,
  label,
  sportSlug,
  query,
  excludeId,
}: {
  teamId: string
  teamName: string
  label: string
  sportSlug: string
  query: { isPending: boolean; data: FixtureSummaryDto[] | undefined }
  excludeId: string
}) {
  // Only matches with a real recorded score can become a snapshot card — never fabricate a 0-0
  // for a fixture whose result somehow isn't in yet.
  const fixtures = (query.data ?? [])
    .filter((f) => f.id !== excludeId)
    .map((f) => ({ fixture: f, scores: fixtureScores(f.final_state) }))
    .filter((row): row is { fixture: FixtureSummaryDto; scores: { homeScore: number; awayScore: number } } => row.scores.homeScore !== undefined && row.scores.awayScore !== undefined)
    .slice(0, 4)

  const statsQueries = useQueries({
    queries: fixtures.map(({ fixture }) => ({
      queryKey: ['sports', 'fixture-statistics', fixture.id],
      queryFn: () => sportsApi.fixtureStatistics(fixture.id),
      staleTime: 5 * 60 * 1000,
    })),
  })

  return (
    <div className="min-w-0">
      <p className="mb-2 font-[var(--cd-font-telemetry)] text-[11px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label} · {teamName}
      </p>
      {query.isPending && (
        <div className="space-y-3">
          <InfinitySkeleton className="h-20" />
          <InfinitySkeleton className="h-20" />
        </div>
      )}
      {!query.isPending && fixtures.length === 0 && (
        <InfinityEmptyState
          icon={Radio}
          title="No recent matches yet"
          description={`${teamName} doesn't have a past match under coverage yet.`}
        />
      )}
      {!query.isPending && fixtures.length > 0 && (
        <div className="space-y-3">
          {fixtures.map(({ fixture: m, scores }, i) => {
            const perspectiveIsHome = m.home_team.id === teamId
            const opponent = perspectiveIsHome ? m.away_team : m.home_team
            const statsRows = statsQueries[i]?.data
            const perspectiveStats = statsRows?.find((row) => row.team_id === teamId)?.stats
            const opponentStats = statsRows?.find((row) => row.team_id === opponent.id)?.stats
            return (
              <MatchSnapshotCard
                key={m.id}
                competition={m.competition_name}
                competitionLogoUrl={m.competition_logo_url}
                dateLabel={new Date(m.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                teamName={teamName}
                teamLogoUrl={perspectiveIsHome ? m.home_team.logo_url : m.away_team.logo_url}
                opponentName={opponent.name}
                opponentLogoUrl={opponent.logo_url}
                perspectiveIsHome={perspectiveIsHome}
                homeScore={scores.homeScore}
                awayScore={scores.awayScore}
                perspectiveStats={perspectiveStats}
                opponentStats={opponentStats}
                statsLoading={statsQueries[i]?.isPending}
                href={`/app/${sportSlug}/matches/${m.id}`}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}
