import { cn } from '@/lib/cn'

/**
 * A "sweep" skeleton — a signal-cyan scan line travels across a hairline-bordered block
 * instead of a flat pulse, echoing the ball-tracking/goal-line reticle sweep named in the
 * motion system. `prefers-reduced-motion` collapses the sweep to a static tone via the
 * `--infinity-motion-sweep-duration: 0ms` override in tokens.infinity.css.
 */
export function InfinitySkeleton({ className }: { className?: string }) {
  return (
    <div className={cn('relative overflow-hidden rounded-infinity-sm border border-infinity-border-hairline bg-infinity-ground-2', className)}>
      <div
        className="absolute inset-y-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-infinity-signal/12 to-transparent"
        style={{
          animation: `infinity-sweep var(--infinity-motion-sweep-duration) ease-in-out infinite`,
        }}
      />
    </div>
  )
}
