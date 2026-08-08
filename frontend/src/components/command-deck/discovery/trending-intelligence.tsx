import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import { TrendingUp } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { CDLabel } from '../primitives/panel'
import { CDTelemetryValue } from '../primitives/telemetry'

/**
 * TrendingIntelligence — real "Highest Confidence" rail, sourced from the existing AI Picks
 * endpoint (`/predictions/picks`, already confidence-ranked, PUBLISHED-only). The brief's other
 * six trending signals (most-followed, biggest rivalry, news activity, KG connectivity, upset
 * probability, highest xG) have no real ranking data anywhere in this app today — deliberately
 * left out rather than invented. Renders nothing when there are no published predictions yet for
 * this sport (a real, common state before any market has been generated).
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
    <section id="trending" className="scroll-mt-24">
      <div className="mb-3 flex items-center gap-2">
        <TrendingUp className="size-3.5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
        <h3 className="font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          Trending intelligence
        </h3>
        <span className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          — highest AI confidence right now
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
          if (!fixture) return null
          return (
            <Link
              key={pick.id}
              to={`/app/${sportSlug}/matches/${fixture.id}`}
              className="w-[280px] shrink-0 snap-start rounded-[var(--cd-radius-lg)] border p-4 transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', boxShadow: 'var(--cd-elevation-1)' }}
            >
              <div className="flex items-center justify-between gap-2">
                <CDLabel>{pick.market_name}</CDLabel>
                <CDTelemetryValue value={`${Math.round(pick.confidence_composite * 100)}%`} size="sm" />
              </div>
              <p className="mt-2 truncate font-[var(--cd-font-body)] text-[13px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
                {fixture.home_team.name} <span style={{ color: 'var(--cd-text-muted)' }}>vs</span> {fixture.away_team.name}
              </p>
              <p className="mt-1 truncate font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                {fixture.competition_name}
              </p>
            </Link>
          )
        })}
      </div>
    </section>
  )
}
