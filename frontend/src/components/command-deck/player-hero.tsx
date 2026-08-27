import { Search } from 'lucide-react'
import type { SportMeta } from '@/lib/hooks/use-sport'
import { domainTint } from './primitives/domain'
import { SportSegmentedControl } from './primitives/sport-segmented-control'

/**
 * PlayerHero — Player Intelligence's opening instrument, same stadium-glow/telemetry-grid
 * atmosphere as Team/Competition Hero. `onSportChange` is optional, same convention `TeamHero`
 * established: omitted on the sport-scoped route (`/app/:sport/players`, where `SportShell`
 * already owns sport switching one level up), supplied on the cross-sport `/app/players`
 * destination. Backdrop crests are the same sport's real team logos (joined in by
 * `usePlayerIntelligence`), never stock player photography — the backend exposes no player
 * headshots.
 */
export function PlayerHero({
  sport,
  onSportChange,
  search,
  onSearchChange,
  backdropLogos,
}: {
  sport: SportMeta
  onSportChange?: (sport: SportMeta) => void
  search: string
  onSearchChange: (value: string) => void
  backdropLogos: string[]
}) {
  return (
    <div
      className="relative overflow-hidden rounded-[var(--cd-radius-2xl)] border border-[var(--cd-glass-3-border)] bg-[var(--cd-glass-3-bg)] p-6 backdrop-blur-[var(--cd-glass-3-blur)] sm:p-9"
      style={{ boxShadow: 'var(--cd-card-shadow-hover)' }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]" aria-hidden="true">
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -left-[10%] -top-[30%] h-[420px] w-[420px] rounded-full opacity-60"
          style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
        />
        <div
          className="animate-hero-glow motion-reduce:animate-none absolute -right-[6%] -top-[10%] h-[340px] w-[340px] rounded-full opacity-40"
          style={{ background: `radial-gradient(circle, ${domainTint('knowledge-graph', 22)} 0%, transparent 70%)`, animationDelay: '3s' }}
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
        {backdropLogos.slice(0, 4).map((url, i) => (
          <img
            key={url + i}
            src={url}
            alt=""
            className="absolute size-24 object-contain opacity-[0.05] blur-[0.5px] sm:size-32"
            style={LOGO_POSITIONS[i % LOGO_POSITIONS.length]}
            loading="lazy"
          />
        ))}
      </div>

      <div className="relative flex flex-col gap-6">
        <div>
          <h1
            className="font-[var(--cd-font-display)] text-[28px] font-semibold leading-tight tracking-[-0.015em] sm:text-[34px]"
            style={{ color: 'var(--cd-text-primary)' }}
          >
            Player Intelligence
          </h1>
          <p className="mt-2.5 max-w-xl font-[var(--cd-font-body)] text-[13.5px] leading-relaxed sm:text-[15px]" style={{ color: 'var(--cd-text-secondary)' }}>
            Explore every {sport.label} player TitanIQ tracks, and jump straight to their team's AI intelligence.
          </p>
        </div>

        <div className="relative w-full max-w-md">
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
          <input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search players, teams, positions…"
            className="h-11 w-full rounded-[var(--cd-radius-md)] border pl-10 pr-3.5 backdrop-blur-md font-[var(--cd-font-body)] text-[13.5px] outline-none transition-colors duration-[var(--cd-motion-snap)] focus:border-[var(--cd-accent)]"
            style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 65%, transparent)', color: 'var(--cd-text-primary)' }}
          />
        </div>

        {onSportChange && <SportSegmentedControl sport={sport} onSportChange={onSportChange} />}
      </div>
    </div>
  )
}

const LOGO_POSITIONS: Array<{ top?: string; bottom?: string; left?: string; right?: string; transform?: string }> = [
  { top: '8%', right: '14%', transform: 'rotate(-8deg)' },
  { bottom: '-6%', right: '28%', transform: 'rotate(6deg)' },
  { top: '38%', right: '2%', transform: 'rotate(-4deg)' },
  { bottom: '10%', left: '48%', transform: 'rotate(10deg)' },
]
