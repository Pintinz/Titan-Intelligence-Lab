import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CalendarClock } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureScores } from '@/lib/sports-status'
import { type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDPanel, CDLabel } from '@/components/command-deck/primitives/panel'
import { CDTelemetryValue } from '@/components/command-deck/primitives/telemetry'
import { ActualVsPredictedCard } from '@/components/command-deck/actual-vs-predicted-card'
import { ErrorState } from '@/components/ui/error-state'
import type { FixtureSummaryDto, FixtureTeamStatisticsDto } from '@/lib/api/types'

type StatKey = string

interface StatGroupDef {
  title: string
  neutral: boolean
  rows: Array<{ key: StatKey; label: string; suffix?: string }>
}

/** Each group's `neutral` flag governs whether a leading value earns visual emphasis. Discipline
 * stats (fouls, cards, turnovers, errors) have no "better" side — a higher count is never treated
 * as a win, per TitanIQ's own directive against betting-style winner framing.
 *
 * Sport-specific: each sport's `TeamStatistics.stat_set` carries a different real vocabulary
 * (see `api_sports_adapter.py`'s per-sport shapes) — football's shots/possession/corners/cards
 * has no basketball or baseball equivalent, so this is keyed by sport rather than one fixed list.
 * `field_goal_pct`/`three_point_pct`/`free_throw_pct` are derived client-side in
 * `deriveShootingPercentages` below, not raw provider fields, since the provider reports
 * made/attempted counts rather than a percentage.
 */
const STAT_GROUPS_BY_SPORT: Record<string, StatGroupDef[]> = {
  football: [
    {
      title: 'Attack',
      neutral: false,
      rows: [
        { key: 'shots_total', label: 'Shots' },
        { key: 'shots_on_target', label: 'Shots on target' },
      ],
    },
    { title: 'Control', neutral: false, rows: [{ key: 'possession_pct', label: 'Possession', suffix: '%' }] },
    { title: 'Set pieces', neutral: false, rows: [{ key: 'corners', label: 'Corners' }] },
    {
      title: 'Discipline',
      neutral: true,
      rows: [
        { key: 'fouls', label: 'Fouls' },
        { key: 'cards_yellow', label: 'Yellow cards' },
        { key: 'cards_red', label: 'Red cards' },
      ],
    },
  ],
  basketball: [
    {
      title: 'Scoring',
      neutral: false,
      rows: [
        { key: 'points', label: 'Points' },
        { key: 'field_goals_made', label: 'Field goals made' },
        { key: 'field_goal_pct', label: 'Field goal %', suffix: '%' },
        { key: 'three_pointers_made', label: '3-pointers made' },
        { key: 'three_point_pct', label: '3-point %', suffix: '%' },
        { key: 'free_throws_made', label: 'Free throws made' },
        { key: 'free_throw_pct', label: 'Free throw %', suffix: '%' },
      ],
    },
    {
      title: 'Hustle',
      neutral: false,
      rows: [
        { key: 'rebounds_total', label: 'Rebounds' },
        { key: 'rebounds_offensive', label: 'Offensive rebounds' },
        { key: 'rebounds_defensive', label: 'Defensive rebounds' },
        { key: 'assists', label: 'Assists' },
        { key: 'steals', label: 'Steals' },
        { key: 'blocks', label: 'Blocks' },
      ],
    },
    {
      title: 'Discipline',
      neutral: true,
      rows: [
        { key: 'turnovers', label: 'Turnovers' },
        { key: 'personal_fouls', label: 'Personal fouls' },
      ],
    },
  ],
  baseball: [
    {
      title: 'Box score',
      neutral: false,
      rows: [
        { key: 'runs', label: 'Runs' },
        { key: 'hits', label: 'Hits' },
      ],
    },
    { title: 'Defense', neutral: true, rows: [{ key: 'errors', label: 'Errors' }] },
  ],
}

/** Adds derived shooting-percentage keys (`field_goal_pct` etc) to a basketball stat row so
 * `STAT_GROUPS_BY_SPORT.basketball` can reference them like any other stat_set key — the
 * provider reports made/attempted counts, never a percentage, so this is arithmetic on real
 * recorded numbers, not a fabricated stat. Only added when the attempted count was recorded and
 * non-zero, so a team with no attempts (rather than zero makes) never shows a misleading 0%. */
function deriveShootingPercentages(stats: Record<string, number>): Record<string, number> {
  const pct = (outKey: string, made: string, attempted: string) => {
    const a = stats[attempted]
    return a ? { [outKey]: Math.round((stats[made] / a) * 1000) / 10 } : {}
  }
  return {
    ...stats,
    ...pct('field_goal_pct', 'field_goals_made', 'field_goals_attempted'),
    ...pct('three_point_pct', 'three_pointers_made', 'three_pointers_attempted'),
    ...pct('free_throw_pct', 'free_throws_made', 'free_throws_attempted'),
  }
}

function joinWithAnd(items: string[]): string {
  if (items.length === 1) return items[0]
  if (items.length === 2) return `${items[0]} and ${items[1]}`
  return `${items.slice(0, -1).join(', ')}, and ${items[items.length - 1]}`
}

/**
 * MatchReviewPage — the AI Review TitanIQ's "Recently Completed Intelligence" links to. Never a
 * plain score page: the emphasis throughout is what TitanIQ predicted, what actually happened,
 * and why — the platform's transparency layer. Every number traces to `predictionsApi.review()`;
 * a market with no resolver or an unfinished fixture reads "Awaiting resolution", never a guess.
 * A per-market "Model Learning Summary (Admin Only)" was in the brief but has no real backing
 * data or role-gating wired up yet — omitted this pass rather than faked.
 */
export default function MatchReviewPage() {
  const sport = useSportParam()
  const { matchId } = useParams<{ matchId: string }>()

  const fixtureQuery = useQuery({
    queryKey: ['sports', 'fixture', matchId],
    queryFn: () => sportsApi.getFixture(matchId!),
    enabled: !!matchId,
  })
  const reviewQuery = useQuery({
    queryKey: ['predictions', 'review', matchId],
    queryFn: () => predictionsApi.review(matchId!),
    enabled: !!matchId,
  })
  const statsQuery = useQuery({
    queryKey: ['sports', 'fixture-statistics', matchId],
    queryFn: () => sportsApi.fixtureStatistics(matchId!),
    enabled: !!matchId,
  })

  if (!sport) return null
  if (fixtureQuery.isPending) {
    return <div className="command-deck rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6" />
  }
  if (fixtureQuery.isError) return <ErrorState error={fixtureQuery.error} onRetry={() => void fixtureQuery.refetch()} />

  const fixture = fixtureQuery.data!

  // Some fixtures reference a team_id the backend can no longer resolve (e.g. after a team
  // merge) and serialize home_team/away_team as null despite the DTO's non-null type — show an
  // honest error rather than crashing on every downstream .name/.id/.logo_url access below.
  if (!fixture.home_team || !fixture.away_team) {
    return <ErrorState error={new Error('Team data is unavailable for this match.')} />
  }

  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const markets = reviewQuery.data?.markets ?? []
  const meta = reviewQuery.data?.meta

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)] bg-[var(--cd-bg)] p-3 sm:p-4 lg:p-6">
      <Link
        to={`/app/${sport.slug}/matches/${fixture.id}`}
        className="inline-flex items-center gap-1 font-[var(--cd-font-body)] text-[13px]"
        style={{ color: 'var(--cd-text-secondary)' }}
      >
        <ArrowLeft className="size-3.5" aria-hidden="true" /> Back to match
      </Link>

      <CDPanel>
        <div className="flex items-center justify-between gap-2">
          <CDLabel tone="accent">AI Match Review</CDLabel>
          {meta && meta.resolved_count > 0 && (
            <span
              className="rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]"
              style={{ backgroundColor: 'var(--cd-accent-muted)', color: 'var(--cd-accent)' }}
            >
              {meta.resolved_count} market{meta.resolved_count === 1 ? '' : 's'} reviewed
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-6 sm:justify-between">
          <div className="flex items-center gap-4 sm:gap-8">
            <TeamCrest team={homeTeam} />
            <p className="font-[var(--cd-font-tabular)] text-3xl font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
              {homeScore ?? '–'} <span style={{ color: 'var(--cd-text-muted)' }}>–</span> {awayScore ?? '–'}
            </p>
            <TeamCrest team={awayTeam} />
          </div>
          {meta && (
            <div className="flex items-center gap-6">
              <div className="text-center">
                <CDTelemetryValue value={meta.accuracy !== null ? `${Math.round(meta.accuracy * 100)}%` : '–'} size="lg" />
                <p className="mt-0.5 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  Overall accuracy
                </p>
              </div>
              <div className="text-center">
                <CDTelemetryValue value={`${meta.correct_count}/${meta.resolved_count}`} size="lg" />
                <p className="mt-0.5 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  Markets correct
                </p>
              </div>
            </div>
          )}
        </div>

        <p className="mt-4 flex items-center justify-center gap-1.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          <CalendarClock className="size-3.5" aria-hidden="true" />
          {fixture.competition_name} · {new Date(fixture.scheduled_at).toLocaleDateString(undefined, { dateStyle: 'medium' })}
        </p>
      </CDPanel>

      {fixture.period_scores && <PeriodScoreTable periodScores={fixture.period_scores} homeTeam={homeTeam} awayTeam={awayTeam} />}

      {statsQuery.isPending ? (
        <div className="h-40 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
      ) : (
        <MatchStatisticsPanel
          statsRows={statsQuery.data ?? []}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
          homeTeamId={fixture.home_team.id}
          awayTeamId={fixture.away_team.id}
          sportCode={sport.code}
        />
      )}

      {reviewQuery.isPending && (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-64 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ))}
        </div>
      )}

      {!reviewQuery.isPending && markets.length === 0 && (
        <CDPanel className="text-center">
          <p className="font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
            TitanIQ never generated intelligence on this fixture, so there's no AI review to show.
          </p>
        </CDPanel>
      )}

      {markets.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {markets.map((market) => (
            <ActualVsPredictedCard key={market.market_id} fixture={fixture} market={market} homeTeam={homeTeam} awayTeam={awayTeam} />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * PeriodScoreTable — the real period-by-period line score (basketball quarters, baseball
 * innings), sourced from `Fixture.period_scores` (verified live against each provider's own
 * `/games` response shape — see `api_sports_adapter.py`). Only renders when the provider has
 * actually reported periods; a `null` entry (not yet played, or overtime that didn't happen)
 * prints as an em dash rather than a fabricated 0. Basketball additionally shows a derived
 * halftime split (Q1 + Q2), real arithmetic on recorded quarters, not a separately-fetched stat.
 */
function PeriodScoreTable({
  periodScores,
  homeTeam,
  awayTeam,
}: {
  periodScores: NonNullable<FixtureSummaryDto['period_scores']>
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  const { kind, home, away } = periodScores
  const periodCount = Math.max(home.length, away.length)
  const regularCount = kind === 'quarter' ? 4 : 9
  const labels = Array.from({ length: periodCount }, (_, i) =>
    i < regularCount ? `${i + 1}` : kind === 'quarter' ? 'OT' : 'X'
  )
  const sum = (values: Array<number | null>) => values.reduce<number | null>((acc, v) => (v === null ? acc : (acc ?? 0) + v), null)
  const homeTotal = sum(home)
  const awayTotal = sum(away)

  const halftime =
    kind === 'quarter' && home[0] !== null && home[1] !== null && away[0] !== null && away[1] !== null
      ? { home: home[0] + home[1], away: away[0] + away[1] }
      : null

  return (
    <CDPanel>
      <CDLabel>{kind === 'quarter' ? 'Quarter-by-quarter' : 'Inning-by-inning'}</CDLabel>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse">
          <thead>
            <tr>
              <th className="w-32 pb-2 text-left font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }} />
              {labels.map((label) => (
                <th key={label} className="w-10 pb-2 text-center font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  {label}
                </th>
              ))}
              <th className="w-12 pb-2 text-center font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-secondary)' }}>
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            <PeriodScoreRow team={homeTeam} values={home} total={homeTotal} />
            <PeriodScoreRow team={awayTeam} values={away} total={awayTotal} />
          </tbody>
        </table>
      </div>
      {halftime && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          Halftime: {homeTeam.name} {halftime.home} – {halftime.away} {awayTeam.name}
        </p>
      )}
    </CDPanel>
  )
}

function PeriodScoreRow({ team, values, total }: { team: TeamRef; values: Array<number | null>; total: number | null }) {
  return (
    <tr className="border-t" style={{ borderColor: 'var(--cd-border-hairline)' }}>
      <td className="py-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {team.logoUrl ? (
            <img src={team.logoUrl} alt="" className="size-4 shrink-0 object-contain" loading="lazy" />
          ) : null}
          <span className="truncate font-[var(--cd-font-body)] text-[12.5px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
            {team.name}
          </span>
        </div>
      </td>
      {values.map((value, i) => (
        <td key={i} className="py-2 text-center font-[var(--cd-font-tabular)] text-[13px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
          {value ?? '—'}
        </td>
      ))}
      <td className="py-2 text-center font-[var(--cd-font-tabular)] text-[14px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
        {total ?? '—'}
      </td>
    </tr>
  )
}

function TeamCrest({ team }: { team: TeamRef }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      {team.logoUrl ? (
        <img src={team.logoUrl} alt="" className="size-12 shrink-0 object-contain sm:size-16" loading="lazy" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-12 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-lg font-semibold sm:size-16"
          style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
        >
          {team.name.charAt(0).toUpperCase()}
        </span>
      )}
      <p className="max-w-[6rem] truncate font-[var(--cd-font-body)] text-[11px] font-medium sm:max-w-[8rem]" style={{ color: 'var(--cd-text-secondary)' }}>
        {team.name}
      </p>
    </div>
  )
}

interface ResolvedStatRow {
  key: StatKey
  label: string
  suffix: string
  home: number | null
  away: number | null
}
interface ResolvedStatGroup {
  title: string
  neutral: boolean
  rows: ResolvedStatRow[]
}

function formatStatValue(value: number, suffix: string): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`
}

/**
 * MatchStatisticsPanel — what actually happened on the pitch, read as one bilateral instrument
 * rather than a stack of scoreboard rows. Every value traces to that fixture's own recorded
 * `TeamStatistics` row; a stat neither side had synced is simply omitted (never padded with a 0),
 * and if nothing was recorded at all the panel says so honestly instead of rendering an empty
 * matrix. Grouped by analytical category (Attack/Control/Set pieces/Discipline) — discipline never
 * gets "winner" emphasis, since a higher foul or card count isn't a positive outcome.
 */
function MatchStatisticsPanel({
  statsRows,
  homeTeam,
  awayTeam,
  homeTeamId,
  awayTeamId,
  sportCode,
}: {
  statsRows: FixtureTeamStatisticsDto[]
  homeTeam: TeamRef
  awayTeam: TeamRef
  homeTeamId: string
  awayTeamId: string
  sportCode: string
}) {
  const rawHomeStats = statsRows.find((r) => r.team_id === homeTeamId)?.stats ?? {}
  const rawAwayStats = statsRows.find((r) => r.team_id === awayTeamId)?.stats ?? {}
  const homeStats = sportCode === 'basketball' ? deriveShootingPercentages(rawHomeStats) : rawHomeStats
  const awayStats = sportCode === 'basketball' ? deriveShootingPercentages(rawAwayStats) : rawAwayStats
  const statGroups = STAT_GROUPS_BY_SPORT[sportCode] ?? STAT_GROUPS_BY_SPORT.football

  const groups: ResolvedStatGroup[] = statGroups.map((group) => ({
    title: group.title,
    neutral: group.neutral,
    rows: group.rows
      .filter(({ key }) => homeStats[key] !== undefined || awayStats[key] !== undefined)
      .map(({ key, label, suffix = '' }) => ({ key, label, suffix, home: homeStats[key] ?? null, away: awayStats[key] ?? null })),
  })).filter((group) => group.rows.length > 0)

  const [revealed, setRevealed] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setRevealed(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const homeLeads: string[] = []
  const awayLeads: string[] = []
  for (const group of groups) {
    if (group.neutral) continue
    for (const row of group.rows) {
      if (row.home === null || row.away === null || row.home === row.away) continue
      ;(row.home > row.away ? homeLeads : awayLeads).push(row.label)
    }
  }
  const profileSentence =
    homeLeads.length && awayLeads.length
      ? `${homeTeam.name} led ${joinWithAnd(homeLeads.map((l) => l.toLowerCase()))}, while ${awayTeam.name} led ${joinWithAnd(awayLeads.map((l) => l.toLowerCase()))}.`
      : homeLeads.length
        ? `${homeTeam.name} led ${joinWithAnd(homeLeads.map((l) => l.toLowerCase()))}.`
        : awayLeads.length
          ? `${awayTeam.name} led ${joinWithAnd(awayLeads.map((l) => l.toLowerCase()))}.`
          : null

  return (
    <CDPanel>
      <CDLabel>Match statistics</CDLabel>

      {groups.length === 0 ? (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          TitanIQ hasn't recorded detailed match statistics for this fixture yet.
        </p>
      ) : (
        <>
          <StatsTeamHeader homeTeam={homeTeam} awayTeam={awayTeam} />

          <div className="mt-5">
            {groups.map((group, i) => (
              <div key={group.title} className={i > 0 ? 'mt-5 border-t pt-5' : ''} style={{ borderColor: 'var(--cd-border-hairline)' }}>
                <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--cd-text-muted)' }}>
                  {group.title}
                </p>
                <div className="mt-2.5 space-y-3.5">
                  {group.rows.map((row) => (
                    <MatchStatRow key={row.key} row={row} neutral={group.neutral} revealed={revealed} homeTeam={homeTeam} awayTeam={awayTeam} />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {profileSentence && (
            <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
              <CDLabel>Match statistical profile</CDLabel>
              <p className="mt-2 font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
                {profileSentence}
              </p>
              {(homeLeads.length > 0 || awayLeads.length > 0) && (
                <div className="mt-3.5 grid grid-cols-2 gap-3">
                  <div>
                    <p className="truncate font-[var(--cd-font-body)] text-[11.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                      {homeTeam.name}
                    </p>
                    <p className="mt-0.5 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: homeLeads.length ? 'var(--cd-text-secondary)' : 'var(--cd-text-muted)' }}>
                      {homeLeads.length ? homeLeads.join(' · ') : 'No category led'}
                    </p>
                  </div>
                  <div>
                    <p className="truncate font-[var(--cd-font-body)] text-[11.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                      {awayTeam.name}
                    </p>
                    <p className="mt-0.5 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: awayLeads.length ? 'var(--cd-text-secondary)' : 'var(--cd-text-muted)' }}>
                      {awayLeads.length ? awayLeads.join(' · ') : 'No category led'}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </CDPanel>
  )
}

/** Compact identity row establishing the two comparison columns the matrix below reads against —
 * real crests when available, an elegant monogram when not, never a fabricated logo. */
function StatsTeamHeader({ homeTeam, awayTeam }: { homeTeam: TeamRef; awayTeam: TeamRef }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <TeamIdentity team={homeTeam} align="left" />
      <span
        className="shrink-0 rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[9.5px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: 'var(--cd-text-muted)', backgroundColor: 'var(--cd-surface-3)' }}
      >
        vs
      </span>
      <TeamIdentity team={awayTeam} align="right" />
    </div>
  )
}

function TeamIdentity({ team, align }: { team: TeamRef; align: 'left' | 'right' }) {
  return (
    <div className={`flex min-w-0 items-center gap-2 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      {team.logoUrl ? (
        <img src={team.logoUrl} alt="" className="size-6 shrink-0 object-contain" loading="lazy" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-6 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[10px] font-semibold"
          style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
        >
          {team.name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="truncate font-[var(--cd-font-body)] text-[13px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
        {team.name}
      </span>
    </div>
  )
}

/**
 * One bilateral comparison row: value / bar-half / label / bar-half / value on larger screens,
 * an intelligently stacked pair on mobile. Bars grow from the shared center line toward whichever
 * side they belong to, in exact proportion to `home / (home + away)`. A leading value earns a
 * restrained accent emphasis — except in a neutral (discipline) group, where neither side is
 * treated as "better."
 */
function MatchStatRow({
  row,
  neutral,
  revealed,
  homeTeam,
  awayTeam,
}: {
  row: ResolvedStatRow
  neutral: boolean
  revealed: boolean
  homeTeam: TeamRef
  awayTeam: TeamRef
}) {
  const { label, suffix, home, away } = row
  const [hoverSide, setHoverSide] = useState<'home' | 'away' | null>(null)

  const total = (home ?? 0) + (away ?? 0)
  const homeRatio = total > 0 ? (home ?? 0) / total : 0.5
  const awayRatio = total > 0 ? (away ?? 0) / total : 0.5
  const leader: 'home' | 'away' | null = neutral || home === null || away === null || home === away ? null : home > away ? 'home' : 'away'

  const homeValueColor = leader === 'home' ? 'var(--cd-text-primary)' : 'var(--cd-text-secondary)'
  const awayValueColor = leader === 'away' ? 'var(--cd-text-primary)' : 'var(--cd-text-secondary)'
  const homeBarColor = leader === 'home' || hoverSide === 'home' ? 'var(--cd-accent)' : 'var(--cd-border-strong)'
  const awayBarColor = leader === 'away' || hoverSide === 'away' ? 'var(--cd-accent)' : 'var(--cd-border-strong)'

  const homeText = home !== null ? formatStatValue(home, suffix) : '—'
  const awayText = away !== null ? formatStatValue(away, suffix) : '—'
  const spokenUnit = suffix === '%' ? ' percent' : ''
  const homeSpoken = home !== null ? `${formatStatValue(home, '')}${spokenUnit}` : 'not recorded'
  const awaySpoken = away !== null ? `${formatStatValue(away, '')}${spokenUnit}` : 'not recorded'
  const rowSummary = `${label}: ${homeTeam.name} ${homeSpoken}, ${awayTeam.name} ${awaySpoken}.`

  return (
    <div role="group" aria-label={rowSummary} className="-mx-2 rounded-[var(--cd-radius-sm)] px-2 py-0.5 transition-colors duration-[var(--cd-motion-snap)] hover:bg-[var(--cd-surface-2)]">
      {/* Desktop / tablet: bilateral grid */}
      <div className="hidden items-center gap-3 sm:grid" style={{ gridTemplateColumns: '48px 1fr 132px 1fr 48px' }} aria-hidden="true">
        <span
          className="shrink-0 text-right font-[var(--cd-font-tabular)] text-[13px] font-semibold tabular-nums transition-colors duration-[var(--cd-motion-base)]"
          style={{ color: homeValueColor }}
          onMouseEnter={() => setHoverSide('home')}
          onMouseLeave={() => setHoverSide(null)}
        >
          {homeText}
        </span>
        <div className="relative h-[3px] overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }} onMouseEnter={() => setHoverSide('home')} onMouseLeave={() => setHoverSide(null)}>
          <div
            className="absolute inset-y-0 right-0 rounded-full transition-[width,background-color] duration-[var(--cd-motion-deliberate)]"
            style={{ width: `${revealed ? homeRatio * 100 : 0}%`, backgroundColor: homeBarColor }}
          />
        </div>
        <span className="text-center font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {label}
        </span>
        <div className="relative h-[3px] overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }} onMouseEnter={() => setHoverSide('away')} onMouseLeave={() => setHoverSide(null)}>
          <div
            className="absolute inset-y-0 left-0 rounded-full transition-[width,background-color] duration-[var(--cd-motion-deliberate)]"
            style={{ width: `${revealed ? awayRatio * 100 : 0}%`, backgroundColor: awayBarColor }}
          />
        </div>
        <span
          className="shrink-0 font-[var(--cd-font-tabular)] text-[13px] font-semibold tabular-nums transition-colors duration-[var(--cd-motion-base)]"
          style={{ color: awayValueColor }}
          onMouseEnter={() => setHoverSide('away')}
          onMouseLeave={() => setHoverSide(null)}
        >
          {awayText}
        </span>
      </div>

      {/* Mobile: stacked pair per metric */}
      <div className="space-y-2 sm:hidden" aria-hidden="true">
        <p className="font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {label}
        </p>
        <MobileStatBar name={homeTeam.name} value={homeText} ratio={revealed ? homeRatio : 0} color={homeBarColor} valueColor={homeValueColor} />
        <MobileStatBar name={awayTeam.name} value={awayText} ratio={revealed ? awayRatio : 0} color={awayBarColor} valueColor={awayValueColor} />
      </div>
    </div>
  )
}

function MobileStatBar({ name, value, ratio, color, valueColor }: { name: string; value: string; ratio: number; color: string; valueColor: string }) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
          {name}
        </span>
        <span className="shrink-0 font-[var(--cd-font-tabular)] text-[13px] font-semibold tabular-nums" style={{ color: valueColor }}>
          {value}
        </span>
      </div>
      <div className="mt-1 h-[3px] overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }}>
        <div className="h-full rounded-full transition-[width,background-color] duration-[var(--cd-motion-deliberate)]" style={{ width: `${ratio * 100}%`, backgroundColor: color }} />
      </div>
    </div>
  )
}

