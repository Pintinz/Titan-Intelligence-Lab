import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, CircleCheck, TriangleAlert, CalendarClock } from 'lucide-react'
import { sportsApi } from '@/lib/api/sports'
import { predictionsApi } from '@/lib/api/predictions'
import { useSportParam } from '@/lib/hooks/use-sport'
import { fixtureScores } from '@/lib/sports-status'
import { resolveOutcomeLabel, humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDPanel, CDLabel } from '@/components/command-deck/primitives/panel'
import { CDConfidenceGauge } from '@/components/command-deck/primitives/gauge'
import { CDDistributionBar, CDTelemetryValue } from '@/components/command-deck/primitives/telemetry'
import { ErrorState } from '@/components/ui/error-state'
import type { FixtureTeamStatisticsDto, MarketReviewDto } from '@/lib/api/types'

type StatKey = keyof NonNullable<FixtureTeamStatisticsDto['stats']>

/** Each group's `neutral` flag governs whether a leading value earns visual emphasis. Discipline
 * stats (fouls, cards) have no "better" side — a higher count is never treated as a win, per
 * TitanIQ's own directive against betting-style winner framing. */
const STAT_GROUPS: Array<{ title: string; neutral: boolean; rows: Array<{ key: StatKey; label: string; suffix?: string }> }> = [
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
]

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
    return <div className="command-deck rounded-[var(--cd-radius-xl)] p-6" style={{ backgroundColor: 'var(--cd-bg)' }} />
  }
  if (fixtureQuery.isError) return <ErrorState error={fixtureQuery.error} onRetry={() => void fixtureQuery.refetch()} />

  const fixture = fixtureQuery.data!
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const markets = reviewQuery.data?.markets ?? []
  const meta = reviewQuery.data?.meta

  return (
    <div className="command-deck space-y-6 rounded-[var(--cd-radius-xl)]" style={{ backgroundColor: 'var(--cd-bg)', padding: '1.5rem' }}>
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

      {statsQuery.isPending ? (
        <div className="h-40 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
      ) : (
        <MatchStatisticsPanel statsRows={statsQuery.data ?? []} homeTeam={homeTeam} awayTeam={awayTeam} homeTeamId={fixture.home_team.id} awayTeamId={fixture.away_team.id} />
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
            <MarketReviewCard key={market.market_id} market={market} homeTeam={homeTeam} awayTeam={awayTeam} />
          ))}
        </div>
      )}
    </div>
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
}: {
  statsRows: FixtureTeamStatisticsDto[]
  homeTeam: TeamRef
  awayTeam: TeamRef
  homeTeamId: string
  awayTeamId: string
}) {
  const homeStats = statsRows.find((r) => r.team_id === homeTeamId)?.stats ?? {}
  const awayStats = statsRows.find((r) => r.team_id === awayTeamId)?.stats ?? {}

  const groups: ResolvedStatGroup[] = STAT_GROUPS.map((group) => ({
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

function MarketReviewCard({ market, homeTeam, awayTeam }: { market: MarketReviewDto; homeTeam: TeamRef; awayTeam: TeamRef }) {
  const resolved = market.is_correct !== null
  const distributionEntries = Object.entries(market.probability_distribution)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)

  return (
    <CDPanel accent={resolved && market.is_correct === true}>
      <div className="flex items-center justify-between gap-2">
        <CDLabel>{market.market_name}</CDLabel>
        {resolved ? (
          <span
            className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.05em]"
            style={{
              color: market.is_correct ? 'var(--cd-positive)' : 'var(--cd-negative)',
              backgroundColor: market.is_correct ? 'var(--cd-positive-muted)' : 'var(--cd-negative-muted)',
            }}
          >
            {market.is_correct ? <CircleCheck className="size-3" aria-hidden="true" /> : <TriangleAlert className="size-3" aria-hidden="true" />}
            {market.is_correct ? 'Correct' : 'Missed'}
          </span>
        ) : (
          <span className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
            Awaiting resolution
          </span>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between gap-4">
        <div>
          <p className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            TitanIQ predicted
          </p>
          <p className="mt-0.5 font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            {resolveOutcomeLabel(market.predicted_value, homeTeam, awayTeam)}
          </p>
          {resolved && (
            <>
              <p className="mt-2 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                Actually happened
              </p>
              <p className="mt-0.5 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                {resolveOutcomeLabel(market.actual_value!, homeTeam, awayTeam)}
              </p>
            </>
          )}
        </div>
        <CDConfidenceGauge value={market.confidence} size={84} label="Confidence" />
      </div>

      {distributionEntries.length > 0 && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Probability distribution</CDLabel>
          <div className="mt-3 space-y-2">
            {distributionEntries.map(([key, probability]) => (
              <CDDistributionBar key={key} label={resolveOutcomeLabel(key, homeTeam, awayTeam)} probability={probability} isTop={key === market.predicted_value} />
            ))}
          </div>
        </div>
      )}

      {(market.top_positive_features.length > 0 || market.top_negative_features.length > 0) && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>Evidence TitanIQ used</CDLabel>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {market.top_positive_features.map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <CircleCheck className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-positive)' }}>
                    +{contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
            {market.top_negative_features.map(([key, contribution]) => (
              <li key={key} className="flex items-start gap-2">
                <TriangleAlert className="mt-0.5 size-3.5 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                  {humanizeFactorKey(key)}{' '}
                  <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-negative)' }}>
                    {contribution.toFixed(2)}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {market.ai_explanation && (
        <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--cd-border-hairline)' }}>
          <CDLabel>{resolved ? (market.is_correct ? 'Why TitanIQ was right' : 'Why TitanIQ was wrong') : 'Why TitanIQ believes this'}</CDLabel>
          <p className="mt-2 font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            {market.ai_explanation}
          </p>
        </div>
      )}
    </CDPanel>
  )
}
