import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarClock, ChevronDown, CircleCheck, TriangleAlert, Sparkles } from 'lucide-react'
import { humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { predictionsApi } from '@/lib/api/predictions'
import { fixtureScores } from '@/lib/sports-status'
import { CDLabel } from '../primitives/panel'
import { CDConfidenceGauge } from '../primitives/gauge'
import { CDButton } from '../primitives/button'
import type { PredictionPickDto, FixtureSummaryDto } from '@/lib/api/types'

interface ConfidenceTier {
  label: string
}

/** The Moderate tier's floor (brief: 65-74% -> Moderate). A curated "strongest recommendations"
 * feed showing a card stamped "Low Confidence" reads as contradictory, so the page-level feed
 * filters to this floor before displaying — exported here so the filter can never drift from the
 * badge thresholds below. */
export const AI_PICK_CONFIDENCE_FLOOR = 0.65

/** The floor for the page's "High Confidence" filter — the same Elite/High bands the card already
 * renders, never a second invented threshold. */
export const AI_PICK_HIGH_CONFIDENCE_FLOOR = 0.85

/** Exact bands from the brief — a pure display mapping over the real, already-computed
 * `confidence_composite`, never a new score. */
function confidenceTier(pct: number): ConfidenceTier {
  if (pct >= 95) return { label: 'Elite' }
  if (pct >= 85) return { label: 'High' }
  if (pct >= 75) return { label: 'Strong' }
  if (pct >= 65) return { label: 'Moderate' }
  return { label: 'Low' }
}

/**
 * AiPickCard — one match, one published prediction, one clear verdict. `matchStatus` decides the
 * action and framing: `upcoming` links to live Match Intelligence, `completed` shows the real
 * final score and links to the existing Match Review page instead — a completed fixture's
 * still-published prediction is historical, never presented as a current recommendation.
 * Evidence drivers (real named features, not the raw internal keys) only fetch on expand — the
 * collapsed card uses `evidence_count`, already free in the bulk `/predictions/picks` response.
 */
export function AiPickCard({
  pick,
  fixture,
  sportSlug,
  matchStatus,
}: {
  pick: PredictionPickDto
  fixture: FixtureSummaryDto
  sportSlug: string
  matchStatus: 'upcoming' | 'completed'
}) {
  const [expanded, setExpanded] = useState(false)
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const confidencePct = Math.round(pick.confidence_composite * 100)
  const probabilityPct = Math.round(pick.probability * 100)
  const tier = confidenceTier(confidencePct)
  const href = matchStatus === 'completed' ? `/app/${sportSlug}/matches/${fixture.id}/review` : `/app/${sportSlug}/matches/${fixture.id}`
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const hasScore = matchStatus === 'completed' && (homeScore !== undefined || awayScore !== undefined)

  const detailQuery = useQuery({
    queryKey: ['predictions', pick.id],
    queryFn: () => predictionsApi.get(pick.id),
    enabled: expanded,
  })

  return (
    <div
      className="group relative flex flex-col gap-4 overflow-hidden rounded-[var(--cd-radius-2xl)] p-5 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
          {fixture.competition_name}
        </span>
        <div className="flex shrink-0 items-center gap-2">
          {matchStatus === 'completed' ? (
            <span className="font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              Completed
            </span>
          ) : (
            <span className="flex items-center gap-1 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              <CalendarClock className="size-3" aria-hidden="true" />
              {new Date(fixture.scheduled_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-center gap-3">
        <TeamCrest team={homeTeam} score={hasScore ? homeScore : undefined} />
        <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          {hasScore ? '–' : 'vs'}
        </span>
        <TeamCrest team={awayTeam} score={hasScore ? awayScore : undefined} />
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
        <div className="relative flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <Sparkles className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
            <CDLabel tone="accent">TitanIQ Top Pick</CDLabel>
          </div>
          {pick.status === 'PUBLISHED' && (
            <span className="font-[var(--cd-font-telemetry)] text-[8.5px] font-medium uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
              Published
            </span>
          )}
        </div>

        <div className="relative mt-3 flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="font-[var(--cd-font-display)] text-[11px] font-medium" style={{ color: 'var(--cd-text-muted)' }}>
              {pick.market_name}
            </p>
            <p className="mt-1 truncate font-[var(--cd-font-display)] text-[22px] font-bold leading-tight" style={{ color: 'var(--cd-text-primary)' }}>
              {predictionValueLabel(pick.value, homeTeam, awayTeam)}
            </p>
            <p className="mt-1.5 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
              <span className="font-[var(--cd-font-tabular)] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                {probabilityPct}%
              </span>{' '}
              probability
            </p>
          </div>
          <CDConfidenceGauge value={pick.confidence_composite} size={76} label={tier.label} />
        </div>

        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="relative mt-3.5 flex w-full items-center justify-between gap-2 border-t pt-3 text-left"
          style={{ borderColor: 'var(--cd-border-hairline)' }}
          aria-expanded={expanded}
        >
          <span className="font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
            {pick.evidence_count > 0 ? `${pick.evidence_count} evidence ${pick.evidence_count === 1 ? 'driver' : 'drivers'}` : 'Evidence'}
          </span>
          <ChevronDown
            className="size-3.5 shrink-0 transition-transform duration-[var(--cd-motion-base)]"
            style={{ color: 'var(--cd-text-muted)', transform: expanded ? 'rotate(180deg)' : undefined }}
            aria-hidden="true"
          />
        </button>

        {!expanded && pick.ai_explanation && (
          <p className="relative mt-1.5 line-clamp-2 font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
            {pick.ai_explanation}
          </p>
        )}

        {expanded && (
          <div className="relative mt-2.5 space-y-3">
            {detailQuery.isPending && (
              <div className="space-y-1.5">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="h-3.5 w-3/4 animate-pulse rounded motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-surface-3)' }} />
                ))}
              </div>
            )}
            {detailQuery.data && (
              <>
                {pick.ai_explanation && (
                  <p className="font-[var(--cd-font-body)] text-[12px] leading-relaxed" style={{ color: 'var(--cd-text-secondary)' }}>
                    {pick.ai_explanation}
                  </p>
                )}
                {(detailQuery.data.explanation.top_positive_features.length > 0 || detailQuery.data.explanation.top_negative_features.length > 0) && (
                  <ul className="space-y-1.5">
                    {detailQuery.data.explanation.top_positive_features.map(([key]) => (
                      <li key={key} className="flex items-start gap-1.5">
                        <CircleCheck className="mt-0.5 size-3 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
                        <span className="font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                          {humanizeFactorKey(key)}
                        </span>
                      </li>
                    ))}
                    {detailQuery.data.explanation.top_negative_features.map(([key]) => (
                      <li key={key} className="flex items-start gap-1.5">
                        <TriangleAlert className="mt-0.5 size-3 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
                        <span className="font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                          {humanizeFactorKey(key)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {detailQuery.data.generated_at && (
                  <p className="font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>
                    Generated {new Date(detailQuery.data.generated_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </div>

      <CDButton variant="primary" size="sm" href={href} className="justify-center">
        {matchStatus === 'completed' ? 'Review Intelligence' : 'View Match Intelligence'}
      </CDButton>
    </div>
  )
}

function TeamCrest({ team, score }: { team: TeamRef; score?: number }) {
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
      {score !== undefined && (
        <p className="font-[var(--cd-font-tabular)] text-[15px] font-bold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
          {score}
        </p>
      )}
    </div>
  )
}
