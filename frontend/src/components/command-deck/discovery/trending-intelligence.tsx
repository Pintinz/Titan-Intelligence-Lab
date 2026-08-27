import { Link } from 'react-router-dom'
import { useQuery, useQueries } from '@tanstack/react-query'
import { TrendingUp, ChevronRight, Crown } from 'lucide-react'
import { predictionsApi } from '@/lib/api/predictions'
import { sportsApi, type SportCode } from '@/lib/api/sports'
import { resolveVerdict } from '@/components/infinity/evidence-explorer'
import { CDLabel } from '../primitives/panel'
import { CDConfidenceGauge } from '../primitives/gauge'
import { domainTint, sportDomainFor } from '../primitives/domain'

function confidenceTierLabel(pct: number): string {
  if (pct >= 95) return 'Elite'
  if (pct >= 85) return 'High'
  if (pct >= 75) return 'Strong'
  return 'Moderate'
}

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
 *
 * Premium-depth pass (2026-08-27): this rail sat on flat `--cd-surface-1` cards while its own
 * sibling on the same page, `DiscoveryMatchCard`, already carries the glass/glow/crest language
 * every other Command Deck surface converged on — the mismatch read as an unfinished corner of an
 * otherwise premium page. Brought up to that same material (glass surface, sport-tinted hover
 * glow, crests with a glow ring) and added two things genuinely specific to a *ranked* rail rather
 * than a plain fixture card: the real `CDConfidenceGauge` arc (already this world's own instrument
 * for reading confidence, reused rather than a second bespoke treatment) with its qualitative tier
 * label, and a "Highest confidence" crown on the single top-ranked card — real derived rank from
 * the API's own confidence ordering, never a fabricated 1/2/3 sequence.
 */
export function TrendingIntelligence({ sportSlug, sportCode }: { sportSlug: string; sportCode: SportCode }) {
  const picksQuery = useQuery({
    queryKey: ['predictions', 'picks', sportCode, 'trending'],
    queryFn: () => predictionsApi.picks({ sport_code: sportCode, limit: 6 }),
  })
  const picks = picksQuery.data ?? []
  const sportDomain = sportDomainFor(sportSlug)

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
            <div
              key={i}
              className="h-[172px] w-[280px] shrink-0 animate-pulse rounded-[var(--cd-radius-xl)] motion-reduce:animate-none"
              style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)' }}
            />
          ))}
        </div>
      )}

      <div className="-mx-1 flex snap-x gap-3.5 overflow-x-auto px-1 pb-2">
        {picks.map((pick, i) => {
          const fixture = fixtureQueries[i]?.data
          if (!fixture || !fixture.home_team || !fixture.away_team) return null
          const homeTeam = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
          const awayTeam = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
          const verdict = resolveVerdict(pick.value, homeTeam, awayTeam)
          const confidencePct = Math.round(pick.confidence_composite * 100)
          const glowTint = sportDomain ? domainTint(sportDomain, 12) : 'var(--cd-accent-muted)'
          const isTopRanked = i === 0

          return (
            <Link
              key={pick.id}
              to={`/app/${sportSlug}/matches/${fixture.id}`}
              className="group relative w-[280px] shrink-0 snap-start overflow-hidden rounded-[var(--cd-radius-xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] ease-out hover:-translate-y-0.5"
              style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
            >
              <div
                className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-[var(--cd-motion-base)] group-hover:opacity-100"
                style={{ background: `radial-gradient(140% 90% at 100% 0%, ${glowTint}, transparent 62%)` }}
                aria-hidden="true"
              />

              <div className="relative z-10 flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1 pr-1">
                  {isTopRanked && (
                    <span
                      className="mb-1.5 flex w-fit items-center gap-1 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-telemetry)] text-[9px] font-semibold uppercase tracking-[0.05em]"
                      style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)', boxShadow: '0 0 0 1px var(--cd-accent-strong) inset' }}
                    >
                      <Crown className="size-2.5" aria-hidden="true" />
                      Top signal
                    </span>
                  )}
                  <CDLabel>{pick.market_name}</CDLabel>
                  <p className="mt-1.5 truncate font-[var(--cd-font-display)] text-[16px] font-bold leading-tight" style={{ color: 'var(--cd-text-primary)' }}>
                    {verdict.text}
                  </p>
                  <p className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
                    {Math.round(pick.probability * 100)}% probability
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-center">
                  <CDConfidenceGauge value={pick.confidence_composite} size={44} />
                  <span className="mt-0.5 font-[var(--cd-font-telemetry)] text-[8.5px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                    {confidenceTierLabel(confidencePct)}
                  </span>
                </div>
              </div>

              <div className="relative z-10 mt-3 space-y-1.5 border-t pt-2.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
                <TeamCrest name={homeTeam.name} logoUrl={homeTeam.logoUrl} glowTint={glowTint} />
                <TeamCrest name={awayTeam.name} logoUrl={awayTeam.logoUrl} glowTint={glowTint} />
              </div>

              <div className="relative z-10 mt-2 flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-1.5">
                  {fixture.competition_logo_url && (
                    <img src={fixture.competition_logo_url} alt="" className="size-3 shrink-0 object-contain" loading="lazy" />
                  )}
                  <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                    {fixture.competition_name}
                  </span>
                </div>
                {pick.evidence_count > 0 && (
                  <span className="shrink-0 font-[var(--cd-font-tabular)] text-[10px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
                    {pick.evidence_count} evidence item{pick.evidence_count === 1 ? '' : 's'}
                  </span>
                )}
              </div>

              <div
                className="group/link relative z-10 mt-2.5 inline-flex items-center gap-0.5 font-[var(--cd-font-body)] text-[11px] font-medium transition-colors"
                style={{ color: 'var(--cd-text-secondary)' }}
              >
                Investigate
                <ChevronRight className="size-3 transition-transform duration-[var(--cd-motion-base)] group-hover:translate-x-0.5" aria-hidden="true" />
              </div>
            </Link>
          )
        })}
      </div>
    </section>
  )
}

function TeamCrest({ name, logoUrl, glowTint }: { name: string; logoUrl?: string | null; glowTint: string }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-1.5">
      <span className="relative flex size-5 shrink-0 items-center justify-center">
        <span
          className="pointer-events-none absolute inset-[-3px] rounded-full opacity-70"
          style={{ background: `radial-gradient(circle, ${glowTint} 0%, transparent 72%)` }}
          aria-hidden="true"
        />
        {logoUrl ? (
          <img src={logoUrl} alt="" className="relative size-5 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span
            aria-hidden="true"
            className="relative flex size-5 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[8px] font-semibold"
            style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
          >
            {name.charAt(0).toUpperCase()}
          </span>
        )}
      </span>
      <span className="truncate font-[var(--cd-font-body)] text-[12px] font-medium" style={{ color: 'var(--cd-text-primary)' }}>
        {name}
      </span>
    </span>
  )
}
