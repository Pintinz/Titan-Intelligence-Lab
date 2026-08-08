import { CalendarClock, Sparkles } from 'lucide-react'
import { resolveVerdict, type TeamRef } from '@/components/infinity/evidence-explorer'
import { CDLabel } from '../primitives/panel'
import { CDConfidenceGauge } from '../primitives/gauge'
import { CDButton } from '../primitives/button'
import type { PredictionPickDto } from '@/lib/api/types'
import type { FixtureSummaryDto } from '@/lib/api/types'

/** Real backend labels this brief asks to never expose raw — everything else (scorelines like
 * "1-0", team-resolved HOME_WIN/AWAY_WIN via `resolveVerdict`) is already human-readable. */
const VALUE_LABELS: Record<string, string> = {
  YES: 'Yes',
  NO: 'No',
  OVER: 'Over',
  UNDER: 'Under',
  positive: 'Yes',
  negative: 'No',
}

function resolvePickLabel(value: string | number, homeTeam: TeamRef, awayTeam: TeamRef): string {
  const stringValue = String(value)
  if (stringValue in VALUE_LABELS) return VALUE_LABELS[stringValue]
  return resolveVerdict(value, homeTeam, awayTeam).text
}

interface ConfidenceTier {
  label: string
}

/** The Moderate tier's floor (brief: 65-74% → Moderate). A curated "strongest recommendations"
 * feed showing a card stamped "Low Confidence" reads as contradictory, so the page-level feed
 * filters to this floor before displaying — exported here so the filter can never drift from the
 * badge thresholds below. */
export const AI_PICK_CONFIDENCE_FLOOR = 0.65

/** Exact bands from the brief — a pure display mapping over the real, already-computed
 * `confidence_composite`, never a new score. */
function confidenceTier(pct: number): ConfidenceTier {
  if (pct >= 95) return { label: 'Elite' }
  if (pct >= 85) return { label: 'High' }
  if (pct >= 75) return { label: 'Strong' }
  if (pct >= 65) return { label: 'Moderate' }
  return { label: 'Low' }
}

export function AiPickCard({
  pick,
  fixture,
  sportSlug,
}: {
  pick: PredictionPickDto
  fixture: FixtureSummaryDto
  sportSlug: string
}) {
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const pct = Math.round(pick.confidence_composite * 100)
  const tier = confidenceTier(pct)
  const href = `/app/${sportSlug}/matches/${fixture.id}`

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-2xl)] p-5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          {fixture.competition_name}
        </span>
        <span className="flex shrink-0 items-center gap-1 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
          <CalendarClock className="size-3" aria-hidden="true" />
          {new Date(fixture.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
        </span>
      </div>

      <div className="flex items-center justify-center gap-3">
        <TeamCrest team={homeTeam} />
        <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>vs</span>
        <TeamCrest team={awayTeam} />
      </div>

      <div
        className="relative overflow-hidden rounded-[var(--cd-radius-lg)] p-4"
        style={{ border: '1px solid var(--cd-accent-strong)', backgroundColor: 'var(--cd-accent-muted)' }}
      >
        <div
          className="pointer-events-none absolute -top-10 -right-10 h-32 w-32 rounded-full opacity-60"
          style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
          aria-hidden="true"
        />
        <div className="relative flex items-center gap-1.5">
          <Sparkles className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
          <CDLabel tone="accent">TitanIQ Top Pick</CDLabel>
        </div>

        <div className="relative mt-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="font-[var(--cd-font-display)] text-[11px] font-medium" style={{ color: 'var(--cd-text-muted)' }}>
              {pick.market_name}
            </p>
            <p className="mt-1 truncate font-[var(--cd-font-display)] text-[22px] font-bold leading-tight" style={{ color: 'var(--cd-text-primary)' }}>
              {resolvePickLabel(pick.value, homeTeam, awayTeam)}
            </p>
          </div>
          <CDConfidenceGauge value={pick.confidence_composite} size={76} label={tier.label} />
        </div>

        {pick.ai_explanation && (
          <div className="relative mt-3.5 border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
            <p className="font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
              Evidence
            </p>
            <p className="mt-1 line-clamp-2 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
              {pick.ai_explanation}
            </p>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <CDButton variant="primary" size="sm" href={href} className="flex-1 justify-center">
          Generate Intelligence
        </CDButton>
        <CDButton variant="secondary" size="sm" href={href}>
          View Match
        </CDButton>
      </div>
    </div>
  )
}

function TeamCrest({ team }: { team: TeamRef }) {
  return (
    <div className="flex flex-1 flex-col items-center gap-1.5 min-w-0">
      <span className="relative flex size-12 shrink-0 items-center justify-center">
        <span
          className="pointer-events-none absolute inset-[-6px] rounded-full opacity-70"
          style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 72%)' }}
          aria-hidden="true"
        />
        {team.logoUrl ? (
          <img src={team.logoUrl} alt="" className="relative size-12 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span
            aria-hidden="true"
            className="relative flex size-12 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[15px] font-semibold"
            style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
          >
            {team.name.charAt(0).toUpperCase()}
          </span>
        )}
      </span>
      <p className="max-w-[7rem] truncate font-[var(--cd-font-body)] text-[12px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {team.name}
      </p>
    </div>
  )
}
