import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger' | 'success'
type Size = 'sm' | 'md' | 'lg' | 'icon'

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-infinity-signal text-infinity-ground-0 hover:bg-infinity-signal-hover shadow-[0_0_0_1px_rgba(0,209,255,0.4)]',
  secondary: 'bg-infinity-ground-2 text-infinity-text-primary border border-infinity-border-default hover:border-infinity-border-strong',
  ghost: 'bg-transparent text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
  outline: 'bg-transparent text-infinity-signal border border-infinity-signal-muted hover:bg-infinity-signal-muted',
  danger: 'bg-transparent text-infinity-danger border border-infinity-danger/30 hover:bg-infinity-danger/10',
  success: 'bg-infinity-success text-infinity-ground-0 hover:brightness-110',
}

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-7 px-2.5 text-[12px] gap-1.5',
  md: 'h-9 px-3.5 text-[13px] gap-2',
  lg: 'h-11 px-5 text-[14px] gap-2',
  icon: 'size-9 p-0',
}

/**
 * Infinity's tactile button — snappier motion (100ms) than a default 200ms transition,
 * a 1px active-state translate (the "tactile" the brief asks for), and a signal-cyan
 * focus ring instead of the legacy accent-teal one, so keyboard focus stays legible
 * against the review-panel dark ground.
 */
export const InfinityButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-infinity-sm font-infinity-body font-medium',
        'transition-[background-color,border-color,color,transform] duration-100 ease-[cubic-bezier(0.2,0,0,1)]',
        'active:translate-y-px disabled:pointer-events-none disabled:opacity-40',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal focus-visible:ring-offset-2 focus-visible:ring-offset-infinity-ground-0',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
      {...props}
    />
  ),
)
InfinityButton.displayName = 'InfinityButton'
