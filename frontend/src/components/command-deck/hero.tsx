import { CalendarClock, MapPin, MessageSquareText, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import { CDLabel } from './primitives/panel'
import { CDStatusDot } from './primitives/status'

type TeamRef = { name: string; logoUrl?: string | null }

/**
 * CommandDeckHero — the page's first viewport, built as a live session-open moment: a real
 * kickoff countdown reading like a ticking instrument, AI-ready as a system-status light rather
 * than a decorative badge. No stadium photography (none exists as real product imagery) — the
 * scene comes from typography, telemetry, and real team identity instead.
 */
export function CommandDeckHero({
  competition,
  aiAvailable,
  live,
  statusLabel,
  homeTeam,
  awayTeam,
  homeScore,
  awayScore,
  countdown,
  scheduledAt,
  venueName,
  following,
  onToggleFollow,
  matchId,
}: {
  competition: string
  aiAvailable: boolean
  live: boolean
  statusLabel: string
  homeTeam: TeamRef
  awayTeam: TeamRef
  homeScore?: number
  awayScore?: number
  countdown: string | null
  scheduledAt: string
  venueName?: string | null
  following: boolean
  onToggleFollow: () => void
  matchId: string
}) {
  const hasFinalScore = homeScore !== undefined && awayScore !== undefined

  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-xl)] border p-6 sm:p-8"
      style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', boxShadow: 'var(--cd-elevation-2)' }}
    >
      {/* Ambient field — a faint radial wash, not photography; the instrument-panel ground itself
          is the atmosphere, matching "no fabricated imagery" and the direction's restraint. */}
      <div
        className="pointer-events-none absolute inset-0 opacity-60"
        style={{ background: 'radial-gradient(120% 100% at 50% -20%, var(--cd-accent-muted), transparent 60%)' }}
        aria-hidden="true"
      />

      <div className="relative flex flex-wrap items-center justify-between gap-3">
        <CDLabel>{competition}</CDLabel>
        <div className="flex items-center gap-4">
          {aiAvailable && <CDStatusDot label="AI Ready" tone="ready" />}
          <CDStatusDot label={statusLabel} tone={live ? 'live' : 'idle'} />
        </div>
      </div>

      <div className="relative mt-8 flex flex-col items-center gap-8 lg:flex-row lg:justify-center lg:gap-16">
        <div className="flex items-center justify-center gap-5 sm:gap-10 lg:gap-14">
          <TeamCrest team={homeTeam} />
          <div className="flex flex-col items-center gap-1.5">
            {hasFinalScore ? (
              <p className="font-[var(--cd-font-tabular)] text-3xl font-semibold tabular-nums sm:text-4xl" style={{ color: 'var(--cd-text-primary)' }}>
                {homeScore} <span style={{ color: 'var(--cd-text-muted)' }}>–</span> {awayScore}
              </p>
            ) : (
              <p className="font-[var(--cd-font-telemetry)] text-[12px] uppercase tracking-[0.1em]" style={{ color: 'var(--cd-text-muted)' }}>
                vs
              </p>
            )}
            {countdown && (
              <p className="whitespace-nowrap font-[var(--cd-font-tabular)] text-[13px] font-medium tabular-nums" style={{ color: 'var(--cd-accent)' }}>
                {countdown}
              </p>
            )}
          </div>
          <TeamCrest team={awayTeam} />
        </div>

        <div className="hidden h-24 w-px shrink-0 lg:block" style={{ backgroundColor: 'var(--cd-border-hairline)' }} aria-hidden="true" />

        <div className="flex flex-col items-center gap-3 lg:items-start">
          <h1 className="text-center font-[var(--cd-font-display)] text-xl font-semibold sm:text-2xl lg:text-left" style={{ color: 'var(--cd-text-primary)' }}>
            {homeTeam.name} <span style={{ color: 'var(--cd-text-muted)' }}>vs</span> {awayTeam.name}
          </h1>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 font-[var(--cd-font-tabular)] text-[12px] tabular-nums lg:justify-start" style={{ color: 'var(--cd-text-secondary)' }}>
            <span className="inline-flex items-center gap-1.5">
              <CalendarClock className="size-3.5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
              {new Date(scheduledAt).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
            {venueName && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="size-3.5" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
                {venueName}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2.5 lg:justify-start">
            <button
              type="button"
              onClick={onToggleFollow}
              className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
              style={{
                borderColor: following ? 'var(--cd-accent)' : 'var(--cd-border-default)',
                backgroundColor: following ? 'var(--cd-accent-muted)' : 'transparent',
                color: following ? 'var(--cd-accent)' : 'var(--cd-text-secondary)',
              }}
              aria-pressed={following}
            >
              <Star className="size-3.5" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
              {following ? 'Following' : 'Follow match'}
            </button>
            <Link
              to={`/app/insights?pin_type=fixture&pin_id=${matchId}`}
              className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] border px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)] hover:brightness-110"
              style={{ borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-secondary)' }}
            >
              <MessageSquareText className="size-3.5" aria-hidden="true" />
              Ask the Assistant
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function TeamCrest({ team }: { team: TeamRef }) {
  return (
    <div className="flex flex-col items-center gap-2">
      {team.logoUrl ? (
        <img src={team.logoUrl} alt="" className="size-14 shrink-0 object-contain sm:size-20" loading="lazy" />
      ) : (
        <span
          aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-xl font-semibold sm:size-20 sm:text-2xl"
          style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
        >
          {team.name.charAt(0).toUpperCase()}
        </span>
      )}
      <p className="max-w-[7rem] truncate font-[var(--cd-font-body)] text-[12px] font-medium sm:max-w-[9rem] sm:text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
        {team.name}
      </p>
    </div>
  )
}
