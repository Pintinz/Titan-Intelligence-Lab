import { Link } from 'react-router-dom'
import { CircleCheck, CircleX } from 'lucide-react'
import type { SportCode } from '@/lib/api/sports'
import { useRecentlyCompletedIntelligence, type ReviewedFixture } from '@/lib/hooks/use-recently-completed-intelligence'
import { fixtureScores } from '@/lib/sports-status'
import { CDTelemetryValue } from '../primitives/telemetry'

/**
 * RecentlyCompletedIntelligence — "AI Match Reviews", never "Completed Matches": the emphasis is
 * TitanIQ's own prediction accuracy, not the score. A completed fixture only appears here once
 * `resolve_for_fixture` has actually recorded a real outcome for at least one of its PUBLISHED
 * predictions (the live reconciliation pipeline does this automatically once a fixture finishes)
 * — most completed fixtures in a fresh dev environment won't qualify yet, and that's an honest
 * empty state, not a bug. Thin wrapper over `useRecentlyCompletedIntelligence` — the shared source
 * of truth this rail and Mission Control's cross-sport section both read from.
 */
export function RecentlyCompletedIntelligence({ sportSlug, sportCode }: { sportSlug: string; sportCode: SportCode }) {
  const { reviewed, isLoading: stillLoading } = useRecentlyCompletedIntelligence([{ code: sportCode, slug: sportSlug }])
  if (!stillLoading && reviewed.length === 0) return null

  return (
    <section id="reviews" className="scroll-mt-24">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Recently completed intelligence
        </h3>
      </div>

      {stillLoading && (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ))}
        </div>
      )}

      {!stillLoading && (
        <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
          {reviewed.map((row) => (
            <ReviewedFixtureCard key={row.fixture.id} row={row} />
          ))}
        </div>
      )}
    </section>
  )
}

/** Shared card markup — used by both this single-sport rail and Mission Control's cross-sport
 * `RecentlyCompletedCrossSport`, so the two never visually drift. */
export function ReviewedFixtureCard({ row }: { row: ReviewedFixture }) {
  const { fixture, sportSlug, review } = row
  const { homeScore, awayScore } = fixtureScores(fixture.final_state)
  const accuracyPct = review.meta.accuracy !== null ? Math.round(review.meta.accuracy * 100) : null
  return (
    <Link
      to={`/app/${sportSlug}/matches/${fixture.id}/review`}
      className="group overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <p className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
        {fixture.competition_name}
      </p>
      <p className="mt-1.5 font-[var(--cd-font-body)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
        {fixture.home_team.name} <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>{homeScore ?? '–'}–{awayScore ?? '–'}</span> {fixture.away_team.name}
      </p>

      <div className="mt-3 flex items-center gap-1.5">
        {review.markets.map((m) => (
          <span key={m.market_id} title={m.market_name}>
            {m.is_correct ? (
              <CircleCheck className="size-4" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
            ) : m.is_correct === false ? (
              <CircleX className="size-4" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
            ) : null}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between border-t pt-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <div>
          <p className="font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
            Accuracy
          </p>
          <CDTelemetryValue value={accuracyPct !== null ? `${accuracyPct}%` : '–'} size="sm" />
        </div>
        <span className="font-[var(--cd-font-body)] text-[11px] font-medium" style={{ color: 'var(--cd-accent)' }}>
          View AI review →
        </span>
      </div>
    </Link>
  )
}
