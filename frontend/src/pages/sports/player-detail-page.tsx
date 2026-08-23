import { useParams, Link } from 'react-router-dom'
import { useQueries, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { ArrowLeft, Radio, Gauge, ClipboardList, ChevronRight, Sparkles, Newspaper, CalendarClock } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { graphApi } from '@/lib/api/graph'
import { marketsApi } from '@/lib/api/markets'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureScores } from '@/lib/sports-status'
import { ApiError } from '@/lib/api/client'
import { ErrorState } from '@/components/ui/error-state'
import { CDPanel, CDLabel } from '@/components/command-deck/primitives/panel'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '@/components/command-deck/primitives/domain'
import { MatchSnapshotCard } from '@/components/command-deck/match-snapshot-card'
import { CompetitionFixtureTimeline } from '@/components/command-deck/competition-fixture-timeline'
import { EntityNewsPanel } from '@/components/command-deck/entity-news-panel'
import { EntityAiInsightUnavailable } from '@/components/command-deck/entity-ai-insight'
import { EntityKnowledgeGraphPanel } from '@/components/command-deck/entity-knowledge-graph'
import { latestByMarket } from '@/components/command-deck/workspace/workspace-tabs'
import { resolveOutcomeLabel } from '@/components/infinity/evidence-explorer'
import type { FixtureSummaryDto, FixtureTeamStatisticsDto, InjuryDto, PredictionMarketDto, TransferDto } from '@/lib/api/types'

type Domain = Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>

/** With/without-appearance impact needs per-fixture appearance resolution — `PlayerStatistics`
 * exists as a table but has no repository or endpoint today (confirmed by direct audit), so this
 * always renders `NO_APPEARANCE_DATA`. The state/data contract is real and complete on purpose: a
 * future appearance-resolution endpoint only has to compute `MatchImpactData` and flip the state
 * the page passes in — nothing about this component's shape would need to change. */
type MatchImpactState = 'AVAILABLE' | 'INSUFFICIENT_DATA' | 'NO_APPEARANCE_DATA' | 'LOADING' | 'ERROR'
interface MatchImpactSplit {
  n: number
  winRatePct: number
  goalsPerMatch: number
  pointsPerMatch: number
}
interface MatchImpactData {
  withPlayer: MatchImpactSplit
  withoutPlayer: MatchImpactSplit
}

/**
 * PlayerDetailPage — Command Deck's Player Intelligence surface. `PlayerSummaryDto` is identity-
 * only (name/position/team/date_of_birth/photo — confirmed by direct audit, no stats, no
 * injury/transfer/prediction data anywhere in the API), so this page never invents a snapshot,
 * performance chart, or player-level prediction. What's real: the player's identity, their team's
 * recent form (labeled honestly as the team's results, not this player's personal involvement —
 * no per-match player appearance link is exposed either), and the player's Knowledge Graph
 * context. Match Impact, Availability, Career, and Predictions stay in the page structure as
 * honest "not currently available" instruments rather than being silently dropped, per product
 * direction — visible proof of what TitanIQ does and doesn't know yet.
 */
export default function PlayerDetailPage() {
  const sport = useSportParam()
  const { playerId } = useParams<{ playerId: string }>()

  const playerQuery = useQuery({
    queryKey: ['sports', 'player', playerId],
    queryFn: () => sportsApi.getPlayer(playerId!),
    enabled: !!playerId,
  })
  const teamId = playerQuery.data?.team_id ?? null
  const teamQuery = useQuery({
    queryKey: ['sports', 'team', teamId],
    queryFn: () => sportsApi.getTeam(teamId!),
    enabled: !!teamId,
  })
  const recentQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'fixtures', 'recent'],
    queryFn: () => sportsApi.teamFixtures(teamId!, 8, 'recent'),
    enabled: !!teamId,
  })
  const upcomingQuery = useQuery({
    queryKey: ['sports', 'team', teamId, 'fixtures', 'upcoming'],
    queryFn: () => sportsApi.teamFixtures(teamId!, 8, 'upcoming'),
    enabled: !!teamId,
  })
  const marketsQuery = useQuery({
    queryKey: ['markets', sport?.code, 'production', 'player-detail'],
    queryFn: () => marketsApi.list({ sport_code: sport!.code, status: 'production' }),
    enabled: !!sport,
  })
  const nextFixture = upcomingQuery.data?.[0]
  const nextFixtureHistoryQuery = useQuery({
    queryKey: ['predictions', 'history', nextFixture?.id],
    queryFn: () => predictionsApi.history(nextFixture!.id),
    enabled: !!nextFixture,
  })
  const kgNodeQuery = useQuery({
    queryKey: ['graph', 'entity', 'player', playerId],
    queryFn: () => graphApi.getEntity('player', playerId!),
    enabled: !!playerId,
  })
  const injuriesQuery = useQuery({
    queryKey: ['sports', 'player', playerId, 'injuries'],
    queryFn: () => sportsApi.playerInjuries(playerId!),
    enabled: !!playerId,
  })
  const transfersQuery = useQuery({
    queryKey: ['sports', 'player', playerId, 'transfers'],
    queryFn: () => sportsApi.playerTransfers(playerId!),
    enabled: !!playerId,
  })
  const kgContextQuery = useQuery({
    queryKey: ['graph', 'context', kgNodeQuery.data?.id],
    queryFn: () => graphApi.context(kgNodeQuery.data!.id, { depth: 1, max_nodes: 12 }),
    enabled: !!kgNodeQuery.data,
  })

  if (!sport) return null

  if (playerQuery.isPending) {
    return (
      <div className="command-deck space-y-6">
        <div className="h-4 w-28 animate-pulse rounded-[var(--cd-radius-sm)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
        <div className="h-40 animate-pulse rounded-[var(--cd-radius-2xl)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
        <div className="grid gap-4 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-32 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ))}
        </div>
      </div>
    )
  }

  if (playerQuery.isError) {
    const notFound = playerQuery.error instanceof ApiError && playerQuery.error.status === 404
    if (notFound) {
      return (
        <div className="command-deck mx-auto max-w-md space-y-4 rounded-[var(--cd-radius-xl)] py-16 text-center">
          <p className="font-[var(--cd-font-display)] text-[18px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            Player not found
          </p>
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
            This player could not be resolved from TitanIQ's data.
          </p>
          <Link
            to={`/app/${sport.slug}/players`}
            className="inline-flex items-center gap-1 font-[var(--cd-font-body)] text-[13px] font-medium"
            style={{ color: 'var(--cd-accent)' }}
          >
            <ArrowLeft className="size-3.5" aria-hidden="true" /> Back to players
          </Link>
        </div>
      )
    }
    return <ErrorState error={playerQuery.error} onRetry={() => void playerQuery.refetch()} />
  }

  const player = playerQuery.data
  const domain = sport.slug as Domain
  const team = teamQuery.data ?? null

  const completedFixtures = (recentQuery.data ?? [])
    .filter((f) => f.status.toLowerCase() === 'completed')
    .map((f) => ({ fixture: f, scores: fixtureScores(f.final_state) }))
    .filter(
      (row): row is { fixture: FixtureSummaryDto; scores: { homeScore: number; awayScore: number } } =>
        row.scores.homeScore !== undefined && row.scores.awayScore !== undefined,
    )
    .slice(0, 6)

  return (
    <div className="command-deck space-y-8">
      <Link
        to={`/app/${sport.slug}/players`}
        className="inline-flex items-center gap-1 font-[var(--cd-font-body)] text-[13px]"
        style={{ color: 'var(--cd-text-secondary)' }}
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" /> Back to players
      </Link>

      <PlayerDetailHero player={player} team={team} sportSlug={sport.slug} domain={domain} />

      <div id="recent-form">
        <div className="mb-4 flex items-center gap-2">
          <Radio className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <p className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            Recent form
          </p>
        </div>
        {!team ? (
          <CDPanel>
            <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
              {player.name} isn't currently assigned to a team, so there's no recent form to show.
            </p>
          </CDPanel>
        ) : (
          <>
            <p className="mb-4 font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
              {team.name}'s results in their last completed fixtures — TitanIQ doesn't yet track this player's individual
              involvement (minutes, goals, assists) per match, so these are the team's results, not a personal log.
            </p>
            {recentQuery.isPending ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-44 animate-pulse rounded-[var(--cd-radius-2xl)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
                ))}
              </div>
            ) : completedFixtures.length === 0 ? (
              <CDPanel>
                <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  No completed fixtures logged for {team.name} yet.
                </p>
              </CDPanel>
            ) : (
              <RecentFormGrid rows={completedFixtures} teamId={team.id} teamName={team.name} sportSlug={sport.slug} />
            )}
          </>
        )}
      </div>

      <MatchImpactSection state="NO_APPEARANCE_DATA" data={null} playerName={player.name} />

      <PlayerRecordsPanel injuriesQuery={injuriesQuery} transfersQuery={transfersQuery} />

      {team && (
        <div id="upcoming-fixtures">
          <div className="mb-4 flex items-center gap-2">
            <CalendarClock className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <p className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
              Upcoming fixtures
            </p>
          </div>
          <p className="mb-4 font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
            {team.name}'s upcoming schedule — TitanIQ doesn't yet confirm {player.name}'s individual availability for a specific
            fixture, so this shows the club's schedule, not a start-XI projection.
          </p>
          {upcomingQuery.isPending ? (
            <div className="h-24 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ) : (upcomingQuery.data ?? []).length === 0 ? (
            <CDPanel>
              <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                No upcoming fixtures scheduled for {team.name} yet.
              </p>
            </CDPanel>
          ) : (
            <CompetitionFixtureTimeline fixtures={upcomingQuery.data!} fallbackSportSlug={sport.slug} aiReady={(marketsQuery.data?.length ?? 0) > 0} />
          )}
        </div>
      )}

      <PlayerPredictionIntelligence
        team={team}
        sportSlug={sport.slug}
        nextFixture={nextFixture}
        historyQuery={nextFixtureHistoryQuery}
        markets={marketsQuery.data ?? []}
      />

      <div id="news">
        <div className="mb-4 flex items-center gap-2">
          <Newspaper className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <p className="font-[var(--cd-font-display)] text-[16px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            News
          </p>
        </div>
        <EntityNewsPanel entityRef={player.id} entityLabel={player.name} />
      </div>

      <EntityAiInsightUnavailable entityLabel={player.name} />

      <EntityKnowledgeGraphPanel nodeQuery={kgNodeQuery} contextQuery={kgContextQuery} entityLabel={player.name} />
    </div>
  )
}

/**
 * Player Prediction Intelligence — no player-scoped prediction market exists anywhere in the
 * backend (confirmed: every real market seeds `entity_type=FIXTURE`, never a player), so this
 * never fabricates a player-level forecast. Instead it points at the one real, already-generated
 * prediction that's genuinely relevant: the player's own club's next fixture, if TitanIQ has
 * generated one for it — reusing the exact same `predictionsApi.history` + `latestByMarket`
 * technique `PredictionIntelligenceSection` (Team Intelligence) already uses, just to decide
 * whether a real link exists rather than rendering the full panel here.
 */
function PlayerPredictionIntelligence({
  team,
  sportSlug,
  nextFixture,
  historyQuery,
  markets,
}: {
  team: { id: string; name: string } | null
  sportSlug: string
  nextFixture: FixtureSummaryDto | undefined
  historyQuery: UseQueryResult<Awaited<ReturnType<typeof predictionsApi.history>>>
  markets: PredictionMarketDto[]
}) {
  const generatedMarket = (() => {
    if (!nextFixture || !historyQuery.data) return null
    const latest = latestByMarket(historyQuery.data)
    const generated = markets.filter((m) => latest.has(m.id))
    // Prefer Match Winner as the headline market — same convention Team/Competition Intelligence
    // already use, so this page never shows a different "primary" market for the same fixture.
    const match = generated.find((m) => m.market_key.endsWith('.match_winner')) ?? generated[0]
    return match ? { market: match, prediction: latest.get(match.id)! } : null
  })()

  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <Sparkles className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Prediction intelligence</CDLabel>
      </div>

      {!team && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          Player-level prediction markets are not currently available.
        </p>
      )}

      {team && !nextFixture && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          Player-specific predictions are not currently supported, and {team.name} has no upcoming fixture under coverage yet.
        </p>
      )}

      {team && nextFixture && historyQuery.isPending && (
        <div className="mt-3 h-12 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
      )}

      {team && nextFixture && !historyQuery.isPending && (
        <>
          <p className="mt-3 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            Player-specific predictions are not currently supported.
            {generatedMarket
              ? ` View ${team.name}'s next fixture's team prediction intelligence below.`
              : ` TitanIQ hasn't generated a prediction for ${team.name}'s next fixture yet.`}
          </p>
          {generatedMarket && (
            <Link
              to={`/app/${nextFixture.sport_code ?? sportSlug}/matches/${nextFixture.id}`}
              className="mt-3 flex items-center justify-between gap-3 rounded-[var(--cd-radius-md)] border p-3 transition-colors duration-[var(--cd-motion-base)] hover:border-[var(--cd-accent)]"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)' }}
            >
              <span className="min-w-0">
                <span className="block truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                  {nextFixture.home_team.name} vs {nextFixture.away_team.name}
                </span>
                <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                  {generatedMarket.market.name} ·{' '}
                  {resolveOutcomeLabel(
                    String(generatedMarket.prediction.value),
                    { name: nextFixture.home_team.name, logoUrl: nextFixture.home_team.logo_url },
                    { name: nextFixture.away_team.name, logoUrl: nextFixture.away_team.logo_url },
                  )}{' '}
                  ({(generatedMarket.prediction.probability * 100).toFixed(1)}%)
                </span>
              </span>
              <ChevronRight className="size-3.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            </Link>
          )}
        </>
      )}
    </CDPanel>
  )
}


function PlayerDetailHero({
  player,
  team,
  sportSlug,
  domain,
}: {
  player: { id: string; name: string; position: string | null; date_of_birth: string | null; team_id: string | null; team_name: string | null }
  team: { id: string; name: string; logo_url: string | null } | null
  sportSlug: string
  domain: Domain
}) {
  const domainColor = CD_DOMAIN_COLOR_VAR[domain]
  const age = player.date_of_birth ? computeAge(player.date_of_birth) : null

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 sm:p-8"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" aria-hidden="true">
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -left-[8%] -top-[35%] h-[360px] w-[360px] rounded-full opacity-50"
          style={{ background: `radial-gradient(circle, ${domainTint(domain, 20)} 0%, transparent 70%)` }}
        />
      </div>

      <div className="relative flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-center gap-4">
          <span
            className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-[var(--cd-radius-lg)] border"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)' }}
          >
            {player.photo_url ? (
              <img src={player.photo_url} alt="" className="size-full object-cover" loading="lazy" />
            ) : (
              <span aria-hidden="true" className="font-[var(--cd-font-display)] text-2xl font-semibold" style={{ color: domainColor }}>
                {player.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="min-w-0">
            <CDLabel tone="accent">Player Intelligence</CDLabel>
            <h1
              className="mt-1 truncate font-[var(--cd-font-display)] text-[24px] font-semibold leading-tight sm:text-[28px]"
              style={{ color: 'var(--cd-text-primary)' }}
            >
              {player.name}
            </h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              {player.position && (
                <span
                  className="rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.06em]"
                  style={{ color: domainColor, backgroundColor: domainTint(domain, 14) }}
                >
                  {player.position}
                </span>
              )}
              {age !== null && (
                <span className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>
                  Age {age}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          {team ? (
            <Link
              to={`/app/${sportSlug}/teams/${team.id}`}
              className="flex items-center gap-2.5 rounded-[var(--cd-radius-md)] border px-3 py-2 transition-colors duration-[var(--cd-motion-base)] hover:border-[var(--cd-accent)]"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)' }}
            >
              {team.logo_url ? (
                <img src={team.logo_url} alt="" className="size-7 shrink-0 object-contain" loading="lazy" />
              ) : (
                <span
                  aria-hidden="true"
                  className="flex size-7 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[11px] font-semibold"
                  style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
                >
                  {team.name.charAt(0).toUpperCase()}
                </span>
              )}
              <span className="max-w-[9rem] truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                {team.name}
              </span>
              <ChevronRight className="size-3.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            </Link>
          ) : (
            <span className="font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>
              Unassigned
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function computeAge(dateOfBirth: string): number {
  const dob = new Date(dateOfBirth)
  const now = new Date()
  let age = now.getFullYear() - dob.getFullYear()
  const hasHadBirthdayThisYear = now.getMonth() > dob.getMonth() || (now.getMonth() === dob.getMonth() && now.getDate() >= dob.getDate())
  if (!hasHadBirthdayThisYear) age -= 1
  return age
}

/** Same shape as Team Detail's Recent Form: real per-fixture statistics via `MatchSnapshotCard`,
 * never a plain scoreline, never a "Generate Intelligence" CTA (the fixture already happened). */
function RecentFormGrid({
  rows,
  teamId,
  teamName,
  sportSlug,
}: {
  rows: Array<{ fixture: FixtureSummaryDto; scores: { homeScore: number; awayScore: number } }>
  teamId: string
  teamName: string
  sportSlug: string
}) {
  const statsQueries = useQueries({
    queries: rows.map(({ fixture }) => ({
      queryKey: ['sports', 'fixture-statistics', fixture.id],
      queryFn: () => sportsApi.fixtureStatistics(fixture.id),
      staleTime: 5 * 60 * 1000,
    })),
  })

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(({ fixture, scores }, i) => {
        const perspectiveIsHome = fixture.home_team.id === teamId
        const opponent = perspectiveIsHome ? fixture.away_team : fixture.home_team
        const statsRows = statsQueries[i]?.data
        const perspectiveStats = statsRows?.find((row: FixtureTeamStatisticsDto) => row.team_id === teamId)?.stats
        const opponentStats = statsRows?.find((row: FixtureTeamStatisticsDto) => row.team_id === opponent.id)?.stats
        return (
          <MatchSnapshotCard
            key={fixture.id}
            competition={fixture.competition_name}
            competitionLogoUrl={fixture.competition_logo_url}
            dateLabel={new Date(fixture.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
            teamName={teamName}
            teamLogoUrl={perspectiveIsHome ? fixture.home_team.logo_url : fixture.away_team.logo_url}
            opponentName={opponent.name}
            opponentLogoUrl={opponent.logo_url}
            perspectiveIsHome={perspectiveIsHome}
            homeScore={scores.homeScore}
            awayScore={scores.awayScore}
            perspectiveStats={perspectiveStats}
            opponentStats={opponentStats}
            statsLoading={statsQueries[i]?.isPending}
            href={`/app/${fixture.sport_code ?? sportSlug}/matches/${fixture.id}/review`}
          />
        )
      })}
    </div>
  )
}

/**
 * MatchImpactSection — TitanIQ's real with/without-player comparison, gated entirely behind
 * `state`. Always `NO_APPEARANCE_DATA` today (no appearance-resolution endpoint exists); the
 * `AVAILABLE` branch is a real, typed rendering path a future data source can activate without
 * touching this component's shape.
 */
function MatchImpactSection({ state, data, playerName }: { state: MatchImpactState; data: MatchImpactData | null; playerName: string }) {
  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <Gauge className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Match impact</CDLabel>
      </div>
      <p className="mt-1.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>
        How does the team perform when {playerName} is available?
      </p>

      {state === 'LOADING' && (
        <div className="mt-4 h-20 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
      )}

      {state === 'ERROR' && (
        <p className="mt-4 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          Match impact could not be loaded.
        </p>
      )}

      {(state === 'NO_APPEARANCE_DATA' || state === 'INSUFFICIENT_DATA') && (
        <div className="mt-4 rounded-[var(--cd-radius-md)] border border-dashed p-4" style={{ borderColor: 'var(--cd-border-default)' }}>
          <p className="font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
            {state === 'INSUFFICIENT_DATA'
              ? 'Insufficient historical appearances to calculate a reliable impact comparison.'
              : "With/without-player analysis isn't currently available for this player."}
          </p>
          <p className="mt-1.5 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
            TitanIQ needs verified per-match appearance data — which fixtures this player started or was substituted into
            — before it can compare real team results with and without them. That capability isn't wired up yet.
          </p>
        </div>
      )}

      {state === 'AVAILABLE' && data && (
        <div className="mt-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <MatchImpactSplitCard label="With player" split={data.withPlayer} />
            <MatchImpactSplitCard label="Without player" split={data.withoutPlayer} />
          </div>
          <p className="font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            {playerName}'s team recorded a {(data.withPlayer.winRatePct - data.withoutPlayer.winRatePct).toFixed(0)} percentage-point
            higher win rate in matches where they appeared, based on {data.withPlayer.n + data.withoutPlayer.n} historical fixtures.
            This reflects a statistical association, not a causal claim.
          </p>
        </div>
      )}
    </CDPanel>
  )
}

function MatchImpactSplitCard({ label, split }: { label: string; split: MatchImpactSplit }) {
  return (
    <div className="rounded-[var(--cd-radius-md)] border p-3.5" style={{ borderColor: 'var(--cd-border-hairline)', backgroundColor: 'var(--cd-surface-2)' }}>
      <p className="font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        {label} · n={split.n}
      </p>
      <p className="mt-1.5 font-[var(--cd-font-tabular)] text-[22px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
        {split.winRatePct.toFixed(0)}%
      </p>
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
        Win rate
      </p>
      <div className="mt-2 flex items-center gap-3 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
        <span>{split.goalsPerMatch.toFixed(1)} goals/match</span>
        <span>{split.pointsPerMatch.toFixed(1)} pts/match</span>
      </div>
    </div>
  )
}

/** Availability and career/transfer history now trace to the real squad-intelligence pipeline
 * (Injury/Transfer repositories + API-Football sync). Player-level predictions are still a real
 * gap — no player-scoped market is seeded anywhere — so that row stays an honest "not currently
 * available" rather than being faked to match the other two. */
function PlayerRecordsPanel({
  injuriesQuery,
  transfersQuery,
}: {
  injuriesQuery: UseQueryResult<InjuryDto[]>
  transfersQuery: UseQueryResult<TransferDto[]>
}) {
  const injuries = injuriesQuery.data ?? []
  const transfers = transfersQuery.data ?? []
  const currentInjury = injuries[0] ?? null

  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <ClipboardList className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Player records</CDLabel>
      </div>
      <div className="mt-3 divide-y" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <div className="flex flex-col gap-1 py-3 first:pt-3 sm:flex-row sm:items-baseline sm:gap-4">
          <p className="w-36 shrink-0 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Availability
          </p>
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
            {injuriesQuery.isPending && 'Checking availability…'}
            {!injuriesQuery.isPending && !currentInjury && 'No reported injuries — available.'}
            {!injuriesQuery.isPending && currentInjury && (
              <>
                {currentInjury.status}
                {currentInjury.reason ? ` — ${currentInjury.reason}` : ''}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-col gap-1 py-3 sm:flex-row sm:items-baseline sm:gap-4">
          <p className="w-36 shrink-0 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Career history
          </p>
          <div className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
            {transfersQuery.isPending && 'Loading transfer history…'}
            {!transfersQuery.isPending && transfers.length === 0 && 'No confirmed transfers on record.'}
            {!transfersQuery.isPending && transfers.length > 0 && (
              <ul className="space-y-1">
                {transfers.slice(0, 5).map((t) => (
                  <li key={t.id}>
                    {t.from_team_name ?? 'Free agent'} → {t.to_team_name ?? 'Unknown club'}
                    {t.transfer_type ? ` (${t.transfer_type})` : ''} — {new Date(t.effective_date).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </CDPanel>
  )
}

