import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * The Infinity system's signature surface — a review-panel with camera-calibration
 * corner ticks instead of a rounded card shell. Every Infinity card/chart/rail composes
 * this rather than a generic bordered div, so the corner-tick motif reads as one
 * consistent "this is evidence" signal across the whole system.
 *
 * `tone` tints the corner ticks and (optionally) the panel's ambient glow — pass a
 * domain or status color to mark whose evidence this is (e.g. `var(--color-infinity-football)`
 * for a football match panel, `var(--color-infinity-live)` for a live match).
 */
export function InfinityPanel({
  children,
  className,
  tone = 'var(--infinity-border-default)',
  glow = false,
  as: Component = 'div',
  id,
}: {
  children: ReactNode
  className?: string
  tone?: string
  glow?: boolean
  as?: 'div' | 'article' | 'section'
  id?: string
}) {
  return (
    <Component
      id={id}
      className={cn(
        'relative border border-infinity-border-hairline bg-infinity-ground-1 p-4',
        'rounded-infinity-md',
        className,
      )}
      style={glow ? { boxShadow: `0 0 0 1px ${tone}40, 0 0 32px ${tone}1f` } : undefined}
    >
      <CornerTick position="top-left" tone={tone} />
      <CornerTick position="top-right" tone={tone} />
      <CornerTick position="bottom-left" tone={tone} />
      <CornerTick position="bottom-right" tone={tone} />
      {children}
    </Component>
  )
}

function CornerTick({
  position,
  tone,
}: {
  position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
  tone: string
}) {
  const positionClass = {
    'top-left': 'left-0 top-0 border-l border-t',
    'top-right': 'right-0 top-0 border-r border-t',
    'bottom-left': 'left-0 bottom-0 border-l border-b',
    'bottom-right': 'right-0 bottom-0 border-r border-b',
  }[position]

  return (
    <span
      aria-hidden="true"
      className={cn('pointer-events-none absolute size-2.5', positionClass)}
      style={{ borderColor: tone }}
    />
  )
}

/** Uppercase, letter-spaced micro-label — the broadcast-lower-third vocabulary used for
 * every panel eyebrow/section tag in the system instead of a plain small heading. */
export function InfinityLabel({ children, tone, className }: { children: ReactNode; tone?: string; className?: string }) {
  return (
    <span
      className={cn('font-infinity-body text-[11px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted', className)}
      style={tone ? { color: tone } : undefined}
    >
      {children}
    </span>
  )
}
