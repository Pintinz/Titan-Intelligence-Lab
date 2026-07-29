import type { CSSProperties, HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Confidence Telemetry — the page's signature element (see design plan).
 *
 * Every Intelligence Card shows confidence as a 4-segment sector bar, never a bare percentage
 * badge. The tier grammar borrows F1 broadcast timing-tower conventions (purple = best-in-class,
 * green = strong, yellow = caution) and remaps them onto TitanIQ's own confidence philosophy —
 * a reliability signal, not a good/bad judgement (docs/design_system.md already draws this line
 * for the rest of the app; this makes it a literal, recognizable visual mark unique to TitanIQ).
 *
 * Tier cutoffs mirror the ConfidenceEngine's own composite scale (0-1) — not invented thresholds:
 * ≥0.85 Peak, ≥0.70 High, ≥0.55 Medium, else Low.
 */
export type ConfidenceTier = 'low' | 'medium' | 'high' | 'peak'

export function tierFromComposite(composite: number): {
  tier: ConfidenceTier
  label: string
  color: string
  dim: string
  lit: number
} {
  if (composite >= 0.85) {
    return { tier: 'peak', label: 'Peak intelligence', color: 'var(--tl-violet)', dim: 'var(--tl-violet-dim)', lit: 4 }
  }
  if (composite >= 0.7) {
    return { tier: 'high', label: 'High confidence', color: 'var(--tl-signal)', dim: 'var(--tl-signal-dim)', lit: 3 }
  }
  if (composite >= 0.55) {
    return { tier: 'medium', label: 'Medium confidence', color: 'var(--tl-amber)', dim: 'var(--tl-amber-dim)', lit: 2 }
  }
  return { tier: 'low', label: 'Low confidence', color: 'var(--tl-ink-faint)', dim: 'transparent', lit: 1 }
}

const BAR_HEIGHTS = ['h-2', 'h-3', 'h-4', 'h-5']

export function ConfidenceTelemetry({
  composite,
  size = 'md',
  className,
}: {
  composite: number
  size?: 'sm' | 'md'
  className?: string
}) {
  const { label, color, dim, lit } = tierFromComposite(composite)
  const pct = Math.round(composite * 100)
  return (
    <div className={cn('flex items-center gap-2.5', className)} role="img" aria-label={`${label}, ${pct}% confidence`}>
      <div className="flex items-end gap-[3px]" aria-hidden="true">
        {BAR_HEIGHTS.map((h, i) => (
          <span
            key={i}
            className={cn('w-[5px] rounded-[1px] transition-colors', h)}
            style={{
              backgroundColor: i < lit ? color : 'var(--tl-steel-line-strong)',
              boxShadow: i < lit ? `0 0 8px 0 ${dim}` : 'none',
            }}
          />
        ))}
      </div>
      <div className="flex flex-col leading-none">
        <span className="tl-mono font-semibold" style={{ color, fontSize: size === 'sm' ? '0.8rem' : '0.9rem' }}>
          {pct}%
        </span>
        {size === 'md' && (
          <span className="tl-eyebrow mt-0.5" style={{ fontSize: '0.6rem', letterSpacing: '0.1em' }}>
            {label}
          </span>
        )}
      </div>
    </div>
  )
}

export function LiveDot({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className="relative flex h-1.5 w-1.5">
        <span className="tl-live-dot absolute inline-flex h-full w-full rounded-full bg-[var(--tl-crimson)]" />
      </span>
      <span className="tl-eyebrow" style={{ color: 'var(--tl-crimson)' }}>
        Live
      </span>
    </span>
  )
}

export function Eyebrow({
  children,
  className,
  style,
}: {
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  return (
    <span className={cn('tl-eyebrow', className)} style={style}>
      {children}
    </span>
  )
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  action,
  className,
}: {
  eyebrow: string
  title: ReactNode
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between', className)}>
      <div className="flex flex-col gap-2">
        <Eyebrow style={{ color: 'var(--tl-signal)' }}>{eyebrow}</Eyebrow>
        <h2 className="tl-display text-3xl sm:text-4xl" style={{ color: 'var(--tl-ink)' }}>
          {title}
        </h2>
        {description && (
          <p className="max-w-xl text-sm" style={{ color: 'var(--tl-ink-dim)' }}>
            {description}
          </p>
        )}
      </div>
      {action}
    </div>
  )
}

/**
 * Every section that renders illustrative (not live) content carries this marker — the honest
 * alternative to silently dumping sample data as if it were real, matching the convention the
 * previous milestone established (docs/frontend_architecture.md §7: sports/prediction/news/KG
 * endpoints all require an authenticated session, so a signed-out visitor never sees live data).
 */
export function IllustrativeTag({ className }: { className?: string }) {
  return (
    <span
      className={cn('tl-mono inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[0.65rem] uppercase tracking-wide', className)}
      style={{ color: 'var(--tl-ink-faint)', border: '1px solid var(--tl-steel-line-strong)' }}
      title="Illustrative example — sign in to see live intelligence for real fixtures"
    >
      Illustrative
    </span>
  )
}

export function Hairline({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('h-px w-full', className)} style={{ backgroundColor: 'var(--tl-steel-line)' }} {...props} />
}

export function Section({
  id,
  className,
  children,
}: {
  id?: string
  className?: string
  children: ReactNode
}) {
  return (
    <section id={id} className={cn('relative mx-auto w-full max-w-[1400px] px-6 py-16 sm:px-10 sm:py-20', className)}>
      {children}
    </section>
  )
}
