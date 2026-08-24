import type { ReactNode } from 'react'

/** Static, literal Tailwind classes per glass level — kept as string literals (not template
 * interpolation) so the JIT scanner actually generates the arbitrary-value CSS for all three;
 * an interpolated `bg-[var(--cd-glass-${level}-bg)]` would never be found at build time. */
const GLASS_SURFACE: Record<1 | 2 | 3, string> = {
  1: 'bg-[var(--cd-glass-1-bg)] border-[var(--cd-glass-1-border)] backdrop-blur-[var(--cd-glass-1-blur)]',
  2: 'bg-[var(--cd-glass-2-bg)] border-[var(--cd-glass-2-border)] backdrop-blur-[var(--cd-glass-2-blur)]',
  3: 'bg-[var(--cd-glass-3-bg)] border-[var(--cd-glass-3-border)] backdrop-blur-[var(--cd-glass-3-blur)]',
}

/**
 * CDPanel — Command Deck's structural surface, now a restrained glass material (Premium
 * Glassmorphism pass) rather than a flat opaque card: translucent surface + backdrop blur + a
 * thin border, at one of three levels (see tokens.command-deck.css's GLASS SYSTEM comment).
 * `accent` — already Command Deck's existing convention for "the panel currently live/primary"
 * (Generated Intelligence, the active Prediction Laboratory market) — now also promotes the
 * panel to glass level 3 (the deepest separation + the only glow), so no caller needed to
 * change to adopt the new hierarchy. Ordinary panels stay at level 2. `glass={false}` opts a
 * panel fully out (flat, no blur) for the rare case where blur cost or legibility over dense
 * scrolling content matters more than the material.
 */
export function CDPanel({
  children,
  className = '',
  accent = false,
  padding = 'default',
  glass = true,
}: {
  children: ReactNode
  className?: string
  accent?: boolean
  padding?: 'default' | 'tight' | 'none'
  glass?: boolean
}) {
  const paddingClass = padding === 'none' ? '' : padding === 'tight' ? 'p-4' : 'p-5 sm:p-6'
  const level = accent ? 3 : 2
  return (
    <div
      className={`rounded-[var(--cd-radius-lg)] border transition-[border-color] duration-[var(--cd-motion-base)] ${
        glass ? `${GLASS_SURFACE[level]} hover:border-[var(--cd-border-strong)]` : 'border-[var(--cd-border-default)] bg-[var(--cd-surface-1)]'
      } ${paddingClass} ${className}`}
      style={{ boxShadow: accent ? 'var(--cd-card-shadow-hover)' : 'var(--cd-card-shadow)' }}
    >
      {children}
    </div>
  )
}

/** Small tracked uppercase label — instrument-panel micro-typography, Barlow Condensed telemetry
 * weight. Used for panel eyebrow rows (never a decorative kicker above a heading — this labels a
 * real data group, e.g. "COMPETITION", "KICKOFF"). */
export function CDLabel({ children, tone = 'muted' }: { children: ReactNode; tone?: 'muted' | 'accent' }) {
  return (
    <span
      className="font-[var(--cd-font-telemetry)] text-[11px] font-medium uppercase tracking-[0.08em]"
      style={{ color: tone === 'accent' ? 'var(--cd-accent)' : 'var(--cd-text-muted)' }}
    >
      {children}
    </span>
  )
}
