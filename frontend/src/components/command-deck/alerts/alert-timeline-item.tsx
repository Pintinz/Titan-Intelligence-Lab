import { Link } from 'react-router-dom'
import { PlayCircle, FlagTriangleRight, Sparkles, ChevronRight, Check } from 'lucide-react'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { parsePredictionChangeValue } from '@/lib/alerts/parse-prediction-change'
import { fixtureScores } from '@/lib/sports-status'
import type { AlertEventDto, FixtureSummaryDto, TeamSummaryDto } from '@/lib/api/types'

const TYPE_META: Record<
  AlertEventDto['alert_type'],
  { icon: typeof PlayCircle; label: string; iconColor: string; iconBg: string; iconRing: string }
> = {
  kickoff: {
    icon: PlayCircle,
    label: 'Kickoff',
    iconColor: 'var(--cd-live)',
    iconBg: 'var(--cd-live-muted)',
    iconRing: 'var(--cd-live-muted)',
  },
  final_result: {
    icon: FlagTriangleRight,
    label: 'Final',
    iconColor: 'var(--cd-text-secondary)',
    iconBg: 'var(--cd-surface-3)',
    iconRing: 'var(--cd-border-default)',
  },
  prediction_changed: {
    icon: Sparkles,
    label: 'Prediction change',
    iconColor: 'var(--cd-accent)',
    iconBg: 'var(--cd-accent-muted)',
    iconRing: 'var(--cd-accent-strong)',
  },
}

/**
 * AlertTimelineItem — one shared skeleton (badge, content, action) so the stream stays scannable,
 * with per-type content and a color/icon signature so Kickoff/Final/Prediction Change never read
 * as identical rows. `fixture`/`team` are whichever real entity `entity_ref` resolved to
 * (`undefined` while resolving, `null` when nothing resolved or the alert followed the other
 * kind) — resolved once at the page level, not re-fetched per row.
 *
 * Prediction-change alerts carry only a new value on the real backend event (no market name, no
 * previous confidence/probability) — the card shows exactly that, honestly, rather than a
 * fabricated before/after delta.
 */
export function AlertTimelineItem({
  event,
  fixture,
  team,
  href,
  onMarkRead,
}: {
  event: AlertEventDto
  fixture: FixtureSummaryDto | null | undefined
  team: TeamSummaryDto | null | undefined
  href: string | null
  onMarkRead: () => void
}) {
  const meta = TYPE_META[event.alert_type]
  const Icon = meta.icon
  const unread = event.read_at === null
  const timeLabel = event.created_at
    ? new Date(event.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    : null

  return (
    <li
      className="group relative flex items-start gap-3.5 rounded-[var(--cd-radius-lg)] border p-4 transition-colors duration-[var(--cd-motion-base)]"
      style={{
        borderColor: unread ? 'var(--cd-accent-strong)' : 'var(--cd-border-hairline)',
        backgroundColor: unread ? 'var(--cd-accent-muted)' : 'var(--cd-surface-1)',
      }}
    >
      <span
        className="flex size-8 shrink-0 items-center justify-center rounded-[var(--cd-radius-md)]"
        style={{ backgroundColor: meta.iconBg, color: meta.iconColor, boxShadow: `0 0 0 1px ${meta.iconRing} inset` }}
        aria-hidden="true"
      >
        <Icon className="size-4" aria-hidden="true" />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.07em]" style={{ color: meta.iconColor }}>
            {meta.label}
          </span>
          {timeLabel && (
            <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              {timeLabel}
            </span>
          )}
        </div>

        <AlertBody event={event} fixture={fixture} team={team} />

        <div className="mt-2 flex items-center justify-between gap-3">
          {href ? (
            <Link
              to={href}
              className="group/link inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors"
              style={{ color: 'var(--cd-text-secondary)' }}
            >
              {event.alert_type === 'prediction_changed' ? 'View Prediction Intelligence' : 'Open Match'}
              <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover/link:translate-x-0.5" aria-hidden="true" />
            </Link>
          ) : (
            <span />
          )}
          {unread && (
            <button
              type="button"
              onClick={onMarkRead}
              aria-label="Mark as read"
              className="inline-flex items-center gap-1 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
              style={{ color: 'var(--cd-accent)' }}
            >
              <Check className="size-3.5" aria-hidden="true" />
              Mark read
            </button>
          )}
        </div>
      </div>
    </li>
  )
}

function AlertBody({
  event,
  fixture,
  team,
}: {
  event: AlertEventDto
  fixture: FixtureSummaryDto | null | undefined
  team: TeamSummaryDto | null | undefined
}) {
  if (event.alert_type === 'prediction_changed') {
    const parsedValue = parsePredictionChangeValue(event.body)
    if (fixture) {
      const homeRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
      const awayRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
      return (
        <div className="mt-1">
          <p className="truncate font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            {fixture.home_team.name} vs {fixture.away_team.name}
          </p>
          <p className="mt-0.5 truncate font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
            {fixture.competition_name}
          </p>
          {parsedValue ? (
            <p className="mt-1.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
              New verdict:{' '}
              <span className="font-semibold" style={{ color: 'var(--cd-accent)' }}>
                {predictionValueLabel(parsedValue, homeRef, awayRef)}
              </span>
            </p>
          ) : (
            <p className="mt-1.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
              {event.body}
            </p>
          )}
        </div>
      )
    }
    return (
      <p className="mt-1 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {event.body}
      </p>
    )
  }

  // kickoff / final_result
  if (fixture) {
    const { homeScore, awayScore } = fixtureScores(fixture.final_state)
    const hasScore = event.alert_type === 'final_result' && (homeScore !== undefined || awayScore !== undefined)
    return (
      <div className="mt-1">
        <p className="truncate font-[var(--cd-font-display)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {hasScore ? (
            <>
              {fixture.home_team.name} {homeScore ?? '–'} — {awayScore ?? '–'} {fixture.away_team.name}
            </>
          ) : (
            <>
              {fixture.home_team.name} vs {fixture.away_team.name}
            </>
          )}
        </p>
        <p className="mt-0.5 truncate font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          {fixture.competition_name}
        </p>
      </div>
    )
  }

  return (
    <div className="mt-1">
      <p className="font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {event.body}
      </p>
      {team && (
        <p className="mt-0.5 font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
          Following: {team.name}
        </p>
      )}
    </div>
  )
}
