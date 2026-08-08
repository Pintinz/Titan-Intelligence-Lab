import { useParams, Link } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Radio, Gauge, Waypoints, ClipboardList, ChevronRight } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { graphApi } from '@/lib/api/graph'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureScores } from '@/lib/sports-status'
import { ApiError } from '@/lib/api/client'
import { ErrorState } from '@/components/ui/error-state'
import { CDPanel, CDLabel } from '@/components/command-deck/primitives/panel'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '@/components/command-deck/primitives/domain'
import { MatchSnapshotCard } from '@/components/command-deck/match-snapshot-card'
import type { FixtureSummaryDto, FixtureTeamStatisticsDto, KgContextDto, KgNodeDto } from '@/lib/api/types'

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
 * only (name/position/team/date_of_birth — confirmed by direct audit, no stats, no photo, no
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
  const kgNodeQuery = useQuery({
    queryKey: ['graph', 'entity', 'player', playerId],
    queryFn: () => graphApi.getEntity('player', playerId!),
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

      <PlayerRecordsPanel />

      <KnowledgeGraphSection nodeQuery={kgNodeQuery} contextQuery={kgContextQuery} playerName={player.name} />
    </div>
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
            <span aria-hidden="true" className="font-[var(--cd-font-display)] text-2xl font-semibold" style={{ color: domainColor }}>
              {player.name.charAt(0).toUpperCase()}
            </span>
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

/** Availability, career/transfer history, and player-level predictions all trace to backend
 * tables or contracts that either don't exist or exist with zero API exposure (confirmed by
 * direct audit — Injury/Transfer tables have no repository, no player-scoped market is seeded
 * anywhere). One compact panel rather than three separate empty cards. */
function PlayerRecordsPanel() {
  const rows: Array<{ label: string; copy: string }> = [
    { label: 'Availability', copy: 'Availability data is not currently recorded for this player.' },
    { label: 'Career history', copy: 'Verified transfer history is not currently available.' },
    { label: 'Player predictions', copy: 'Player-level prediction markets are not currently available.' },
  ]
  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <ClipboardList className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Player records</CDLabel>
      </div>
      <div className="mt-3 divide-y" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {rows.map((row) => (
          <div key={row.label} className="flex flex-col gap-1 py-3 first:pt-3 sm:flex-row sm:items-baseline sm:gap-4">
            <p
              className="w-36 shrink-0 font-[var(--cd-font-telemetry)] text-[10.5px] font-semibold uppercase tracking-[0.06em]"
              style={{ color: 'var(--cd-text-muted)' }}
            >
              {row.label}
            </p>
            <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
              {row.copy}
            </p>
          </div>
        ))}
      </div>
    </CDPanel>
  )
}

function KnowledgeGraphSection({
  nodeQuery,
  contextQuery,
  playerName,
}: {
  nodeQuery: { isPending: boolean; isError: boolean; error: unknown; data: KgNodeDto | undefined }
  contextQuery: { isPending: boolean; data: KgContextDto | undefined }
  playerName: string
}) {
  const notFound = nodeQuery.isError && nodeQuery.error instanceof ApiError && nodeQuery.error.status === 404
  const otherError = nodeQuery.isError && !notFound

  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <Waypoints className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Connected intelligence</CDLabel>
      </div>

      {nodeQuery.isPending && (
        <div className="mt-4 h-10 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
      )}

      {notFound && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          No connected entities are currently available for {playerName}.
        </p>
      )}

      {otherError && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          Connected intelligence could not be loaded.
        </p>
      )}

      {nodeQuery.data && (
        <>
          {contextQuery.isPending && (
            <div className="mt-3 h-8 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          )}
          {contextQuery.data &&
            (() => {
              const related = Object.entries(contextQuery.data.related_by_type)
              const total = related.reduce((sum, [, nodes]) => sum + nodes.length, 0)
              if (total === 0) {
                return (
                  <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    No connected entities are currently available for {playerName}.
                  </p>
                )
              }
              return (
                <>
                  <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    TitanIQ has connected {playerName} to {total} related {total === 1 ? 'entity' : 'entities'} it uses to build
                    understanding.
                  </p>
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {related.map(([type, nodes]) => (
                      <li key={type}>
                        <span
                          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-[var(--cd-font-telemetry)] text-[10.5px] font-medium"
                          style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)' }}
                        >
                          {nodes.length} {humanizePlural(type, nodes.length)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )
            })()}
        </>
      )}
    </CDPanel>
  )
}

function humanizePlural(nodeType: string, count: number): string {
  const label = nodeType.replace(/_/g, ' ')
  if (count === 1 || label.endsWith('s')) return label
  return `${label}s`
}
