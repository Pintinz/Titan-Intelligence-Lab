import { ArrowUpRight, MapPin } from 'lucide-react'
import { cn } from '@/lib/cn'
import { FEATURED_MATCHES } from '@/pages/landing/sample-data'
import { ConfidenceTelemetry } from '@/pages/landing/telemetry'

type FeaturedMatch = (typeof FEATURED_MATCHES)[number]

const SPORT_LABEL: Record<string, string> = {
  football: 'Football',
  basketball: 'Basketball',
  baseball: 'Baseball',
  table_tennis: 'Table Tennis',
}

/**
 * The Featured Match Intelligence card — every field the brief asks for (competition, teams,
 * kickoff, prediction, confidence, highlights, news, pulse, "why it matters", open-intelligence
 * CTA), built around the Confidence Telemetry signature rather than a plain score badge.
 */
export function IntelligenceCard({ match, className }: { match: FeaturedMatch; className?: string }) {
  const { seed, fixture } = match
  return (
    <article
      className={cn(
        'group flex w-[320px] shrink-0 snap-start flex-col gap-4 rounded-xl p-5 transition-transform duration-200 ease-out hover:-translate-y-1 sm:w-[360px]',
        className,
      )}
      style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}
    >
      <div className="flex items-center justify-between">
        <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)' }}>
          {SPORT_LABEL[seed.sport]} · {fixture.competition_name}
        </span>
        <span className="tl-mono text-xs" style={{ color: 'var(--tl-ink-faint)' }}>
          {seed.kickoff}
        </span>
      </div>

      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-1 flex-col gap-1">
          <span className="tl-display text-xl leading-none" style={{ color: 'var(--tl-ink)' }}>
            {fixture.home_team.name}
          </span>
          <span className="tl-eyebrow text-[0.65rem]" style={{ color: 'var(--tl-ink-faint)' }}>
            vs
          </span>
          <span className="tl-display text-xl leading-none" style={{ color: 'var(--tl-ink)' }}>
            {fixture.away_team.name}
          </span>
        </div>
        <div className="flex flex-col items-end gap-1 text-right">
          <MapPin className="h-3.5 w-3.5" style={{ color: 'var(--tl-ink-faint)' }} aria-hidden="true" />
          <span className="text-xs" style={{ color: 'var(--tl-ink-faint)' }}>
            {seed.venue}
          </span>
        </div>
      </div>

      <div className="rounded-lg p-3" style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}>
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium" style={{ color: 'var(--tl-ink)' }}>
            {seed.pick}
          </span>
          <span className="tl-mono text-xs" style={{ color: 'var(--tl-ink-dim)' }}>
            {seed.market}
          </span>
        </div>
        <ConfidenceTelemetry composite={seed.composite} size="sm" />
      </div>

      <p className="text-xs leading-relaxed" style={{ color: 'var(--tl-ink-dim)' }}>
        <span className="tl-eyebrow mr-1" style={{ color: 'var(--tl-signal)', fontSize: '0.6rem' }}>
          Why it matters
        </span>
        {seed.whyItMatters}
      </p>

      <div className="flex flex-col gap-1.5 text-xs" style={{ color: 'var(--tl-ink-faint)' }}>
        <div className="flex gap-1.5">
          <span className="shrink-0" style={{ color: 'var(--tl-ink-dim)' }}>
            News
          </span>
          <span className="line-clamp-1">{seed.newsHighlight}</span>
        </div>
        <div className="flex gap-1.5">
          <span className="shrink-0" style={{ color: 'var(--tl-ink-dim)' }}>
            Pulse
          </span>
          <span className="line-clamp-1">{seed.pulseNote}</span>
        </div>
      </div>

      <button
        type="button"
        className="tl-eyebrow mt-1 flex items-center justify-center gap-1.5 rounded-md py-2 transition-colors"
        style={{ border: '1px solid var(--tl-steel-line-strong)', color: 'var(--tl-ink)' }}
      >
        Open Match Intelligence
        <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" aria-hidden="true" />
      </button>
    </article>
  )
}
