import type { ReactNode } from 'react'

/**
 * CDPanel — Command Deck's structural surface. Deliberately flatter than Infinity's glass
 * panels: a bounded instrument reading, not an ambient card. `accent` puts a 1px accent ring +
 * soft glow on the panel (reserved for the panel currently "live" — the active market in the
 * Prediction Laboratory, the Generated Intelligence centerpiece) so the accent stays meaningful
 * rather than decorating every panel on the page.
 */
export function CDPanel({
  children,
  className = '',
  accent = false,
  padding = 'default',
}: {
  children: ReactNode
  className?: string
  accent?: boolean
  padding?: 'default' | 'tight' | 'none'
}) {
  const paddingClass = padding === 'none' ? '' : padding === 'tight' ? 'p-4' : 'p-5 sm:p-6'
  return (
    <div
      className={`rounded-[var(--cd-radius-lg)] border bg-[var(--cd-surface-1)] ${paddingClass} ${className}`}
      style={{
        borderColor: accent ? 'transparent' : 'var(--cd-border-default)',
        boxShadow: accent ? 'var(--cd-elevation-accent)' : 'var(--cd-elevation-1)',
      }}
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
