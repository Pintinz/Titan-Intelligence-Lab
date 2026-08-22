import { Search } from 'lucide-react'
import type { SportMeta } from '@/lib/hooks/use-sport'
import { domainTint } from './primitives/domain'
import { SportSegmentedControl } from './primitives/sport-segmented-control'

/**
 * ContextHero — the Context destination's opening instrument, same template as Matches/Team/
 * Competition/Player Hero. News is cross-sport (the real search/timeline/impact endpoints take
 * no sport filter); the sport switcher scopes only the Injuries/Transfers section below, which is
 * bounded to the user's own followed teams per sport — labelled explicitly so that split reads
 * as intentional, not inconsistent.
 */
export function ContextHero({
  sport,
  onSportChange,
  search,
  onSearchChange,
}: {
  sport: SportMeta
  onSportChange: (sport: SportMeta) => void
  search: string
  onSearchChange: (value: string) => void
}) {
  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] p-6 sm:p-9"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" aria-hidden="true">
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -left-[10%] -top-[30%] h-[420px] w-[420px] rounded-full opacity-60"
          style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
        />
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -right-[6%] -top-[10%] h-[340px] w-[340px] rounded-full opacity-40"
          style={{ background: `radial-gradient(circle, ${domainTint('news', 22)} 0%, transparent 70%)`, animationDelay: '3s' }}
        />
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(var(--cd-text-primary) 1px, transparent 1px), linear-gradient(90deg, var(--cd-text-primary) 1px, transparent 1px)',
            backgroundSize: '48px 48px',
            maskImage: 'radial-gradient(ellipse 85% 65% at 50% 0%, black 0%, transparent 72%)',
            WebkitMaskImage: 'radial-gradient(ellipse 85% 65% at 50% 0%, black 0%, transparent 72%)',
          }}
        />
      </div>

      <div className="relative flex flex-col gap-6">
        <div>
          <h1
            className="font-[var(--cd-font-display)] text-[28px] font-semibold leading-tight tracking-[-0.015em] sm:text-[34px]"
            style={{ color: 'var(--cd-text-primary)' }}
          >
            Context
          </h1>
          <p className="mt-2.5 max-w-xl font-[var(--cd-font-body)] text-[13.5px] leading-relaxed sm:text-[15px]" style={{ color: 'var(--cd-text-secondary)' }}>
            What real-world information could affect TitanIQ's intelligence — news, and injury/transfer activity for the teams you follow.
          </p>
        </div>

        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search news…"
            className="h-11 w-full rounded-[var(--cd-radius-md)] border pl-10 pr-3.5 backdrop-blur-md font-[var(--cd-font-body)] text-[13.5px] outline-none transition-colors duration-[var(--cd-motion-snap)] focus:border-[var(--cd-accent)]"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 65%, transparent)', color: 'var(--cd-text-primary)' }}
          />
        </div>

        <div>
          <p className="mb-2 font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.07em]" style={{ color: 'var(--cd-text-muted)' }}>
            Injuries &amp; transfers sport
          </p>
          <SportSegmentedControl sport={sport} onSportChange={onSportChange} />
        </div>
      </div>
    </div>
  )
}
