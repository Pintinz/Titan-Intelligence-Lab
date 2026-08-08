import { Link } from 'react-router-dom'
import { ChevronRight, Goal, Target, Flag, Crosshair, ShieldCheck, PieChart, RectangleVertical } from 'lucide-react'
import { buildMatchSnapshot, type MatchStats, type MatchResult, type SnapshotStatChip } from '@/lib/match-snapshot'

const STAT_ICONS: Record<SnapshotStatChip['key'], typeof Goal> = {
  goals: Goal,
  btts: Target,
  corners: Flag,
  shots_on_target: Crosshair,
  clean_sheet: ShieldCheck,
  possession: PieChart,
  cards: RectangleVertical,
}

const RESULT_LABEL: Record<MatchResult, string> = { win: 'Win', draw: 'Draw', loss: 'Loss' }

/**
 * AI Match Snapshot — a past match read as a miniature intelligence report rather than a
 * scoreline row (Recent Form redesign brief). Stat chips and the summary sentence both come
 * straight from `buildMatchSnapshot` (deterministic, no LLM) — this component only lays out
 * whatever that function actually returns, never invents a chip on its own.
 */
export function MatchSnapshotCard({
  competition,
  competitionLogoUrl,
  dateLabel,
  teamName,
  teamLogoUrl,
  opponentName,
  opponentLogoUrl,
  perspectiveIsHome,
  homeScore,
  awayScore,
  perspectiveStats,
  opponentStats,
  statsLoading,
  href,
}: {
  competition: string
  competitionLogoUrl?: string | null
  dateLabel: string
  teamName: string
  teamLogoUrl?: string | null
  opponentName: string
  opponentLogoUrl?: string | null
  perspectiveIsHome: boolean
  homeScore: number
  awayScore: number
  perspectiveStats?: MatchStats
  opponentStats?: MatchStats
  statsLoading?: boolean
  href: string
}) {
  const snapshot = buildMatchSnapshot({
    teamName,
    perspectiveIsHome,
    homeScore,
    awayScore,
    perspectiveStats,
    opponentStats,
  })
  const resultTone =
    snapshot.result === 'win'
      ? { fg: 'var(--cd-positive)', bg: 'var(--cd-positive-muted)' }
      : snapshot.result === 'loss'
        ? { fg: 'var(--cd-danger)', bg: 'var(--cd-danger-muted)' }
        : { fg: 'var(--cd-text-secondary)', bg: 'var(--cd-surface-3)' }

  return (
    <div
      className="group relative flex flex-col gap-3 overflow-hidden rounded-[var(--cd-radius-2xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <Link to={href} aria-label={`${teamName} vs ${opponentName}`} className="absolute inset-0 z-0" />

      <div className="relative z-10 flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          {competitionLogoUrl && <img src={competitionLogoUrl} alt="" className="size-3.5 shrink-0 object-contain" loading="lazy" />}
          <span className="truncate">{competition}</span>
        </span>
        <span className="shrink-0 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
          {dateLabel}
        </span>
      </div>

      <div className="relative z-10 flex items-center gap-3">
        <TeamCrestName name={teamName} logoUrl={teamLogoUrl} align="left" />
        <div className="flex shrink-0 flex-col items-center gap-1">
          <span className="font-[var(--cd-font-tabular)] text-[19px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {perspectiveIsHome ? `${homeScore}–${awayScore}` : `${awayScore}–${homeScore}`}
          </span>
          <span
            className="rounded-full px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]"
            style={{ color: resultTone.fg, backgroundColor: resultTone.bg }}
          >
            {RESULT_LABEL[snapshot.result]}
          </span>
        </div>
        <TeamCrestName name={opponentName} logoUrl={opponentLogoUrl} align="right" />
      </div>

      <div className="relative z-10 flex flex-wrap gap-1.5 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {statsLoading
          ? Array.from({ length: 3 }).map((_, i) => (
              <span key={i} className="h-6 w-16 animate-pulse rounded-full motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
            ))
          : snapshot.stats.map((stat) => <StatChip key={stat.key} stat={stat} />)}
      </div>

      <div className="relative z-10 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <p className="font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          AI Match Snapshot
        </p>
        <p className="mt-1 font-[var(--cd-font-body)] text-[12.5px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
          {snapshot.summary}
        </p>
      </div>

      <Link
        to={href}
        className="group/link relative z-10 inline-flex w-fit items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
        style={{ color: 'var(--cd-accent)' }}
      >
        View match <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
      </Link>
    </div>
  )
}

function StatChip({ stat }: { stat: SnapshotStatChip }) {
  const Icon = STAT_ICONS[stat.key]
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
      style={{ backgroundColor: 'var(--cd-surface-2)', border: '1px solid var(--cd-border-hairline)' }}
    >
      <Icon className="size-3" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
      <span className="font-[var(--cd-font-body)] text-[10.5px]" style={{ color: 'var(--cd-text-muted)' }}>
        {stat.label}
      </span>
      <span className="font-[var(--cd-font-tabular)] text-[11px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
        {stat.value}
      </span>
    </span>
  )
}

function TeamCrestName({ name, logoUrl, align }: { name: string; logoUrl?: string | null; align: 'left' | 'right' }) {
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-2 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      {logoUrl ? (
        <img src={logoUrl} alt="" className="size-7 shrink-0 object-contain" loading="lazy" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-7 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[11px] font-semibold"
          style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
        >
          {name.charAt(0).toUpperCase()}
        </span>
      )}
      <span className="truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {name}
      </span>
    </div>
  )
}
