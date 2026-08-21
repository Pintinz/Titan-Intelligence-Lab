import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { resolveVerdict } from '@/components/infinity/evidence-explorer'
import { CDLabel } from '../primitives/panel'

/**
 * TrendingIntelligence ("Priority Intelligence") — real "Highest Confidence" rail, sourced from
 * the existing AI Picks endpoint (`/predictions/picks`, already confidence-ranked, PUBLISHED-
 * only). The brief's other six trending signals (most-followed, biggest rivalry, news activity, KG
 * connectivity, upset probability, highest xG) have no real ranking data anywhere in this app
 * today — deliberately left out rather than invented. Renders nothing when there are no published
 * predictions yet for this sport (a real, common state before any market has been generated).
 *
 * Intelligence Center §8 fix: the card used to show only `confidence_composite` as a bare
 * percentage next to the market name — with no predicted outcome ever shown, a reader had no way
 * to tell that number was confidence rather than a win probability. It now shows both, separately
 * labeled: the real verdict (`value`/`probability`, via the same `resolveVerdict` the match-detail
 * page uses) and confidence as its own badge — never merged into one number. The badge is
 * deliberately labeled "Confidence," not "Intelligence Signal": that name is reserved for a
 * purpose-built priority score (Phase B) this card doesn't compute yet.
 */
export function TrendingIntelligence({ sportSlug, sportCode }: { sportSlug: string; sportCode: SportCode }) {
  const picksQuery = useQuery({
    queryKey: ['predictions', 'picks', sportCode, 'trending'],
    queryFn: () => predictionsApi.picks({ sport_code: sportCode, limit: 6 }),
  })
  const picks = picksQuery.data ?? []

  const fixtureQueries = useQueries({
    queries: picks.map((pick) => ({
      queryKey: ['sports', 'fixture', pick.subject_ref],
      queryFn: () => sportsApi.getFixture(pick.subject_ref),
      enabled: picks.length > 0,
    })),
  })

  if (!picksQuery.isPending && picks.length === 0) return null

  return (
    <section id="priority-intelligence" className="scroll-mt-24">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Priority intelligence
        </h3>
        <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          — ranked by real model confidence
        </span>
      </div>

      {picksQuery.isPending && (
        <div className="flex gap-3.5 overflow-x-auto pb-1">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-28 w-[280px] shrink-0 animate-pulse rounded-[var(--cd-radius-lg)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
          ))}
        </div>
      )}

      <div className="-mx-1 flex snap-x gap-3.5 overflow-x-auto px-1 pb-1">
        {picks.map((pick, i) => {
          const fixture = fixtureQueries[i]?.data
          if (!fixture || !fixture.home_team || !fixture.away_team) return null
          const verdict = resolveVerdict(
            pick.value,
            { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url },
            { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url },
          )
          return (
            <Link
              key={pick.id}
              to={`/app/${sportSlug}/matches/${fixture.id}`}
              className="w-[280px] shrink-0 snap-start rounded-[var(--cd-radius-lg)] border p-4 transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', boxShadow: 'var(--cd-elevation-1)' }}
            >
              <CDLabel>{pick.market_name}</CDLabel>

              <div className="mt-2 flex items-end justify-between gap-2">
                <div>
                  <p className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
                    {verdict.text}
                  </p>
                  <p className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                    {Math.round(pick.probability * 100)}% probability
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-[var(--cd-font-tabular)] text-[15px] font-semibold tabular-nums" style={{ color: 'var(--cd-accent)' }}>
                    {Math.round(pick.confidence_composite * 100)}%
                  </p>
                  <p className="font-[var(--cd-font-telemetry)] text-[9px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                    Confidence
                  </p>
                </div>
              </div>

              <p className="mt-3 truncate border-t pt-2 font-[var(--cd-font-body)] text-[13px] font-medium" style={{ borderColor: 'var(--cd-border-hairline)', color: 'var(--cd-text-primary)' }}>
                {fixture.home_team.name} <span style={{ color: 'var(--cd-text-muted)' }}>vs</span> {fixture.away_team.name}
              </p>
              <div className="mt-1 flex items-center justify-between gap-2">
                <p className="truncate font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                  {fixture.competition_name}
                </p>
                {pick.evidence_count > 0 && (
                  <p className="shrink-0 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                    {pick.evidence_count} evidence item{pick.evidence_count === 1 ? '' : 's'}
                  </p>
                )}
              </div>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
