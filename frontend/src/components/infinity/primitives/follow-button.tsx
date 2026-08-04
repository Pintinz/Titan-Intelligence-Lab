import { Star } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * The Watchlist follow toggle shared by every card that can be followed (match/team/
 * competition). Cards render inside a `<Link>` in every list page, so this always stops
 * propagation/prevents default — otherwise clicking the star would also navigate.
 */
export function InfinityFollowButton({
  following,
  onToggle,
  label,
}: {
  following: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <button
      type="button"
      aria-pressed={following}
      aria-label={following ? `Unfollow ${label}` : `Follow ${label}`}
      onClick={(e) => {
        e.preventDefault()
        e.stopPropagation()
        onToggle()
      }}
      className={cn(
        'inline-flex size-6 shrink-0 items-center justify-center rounded-full transition-colors duration-100',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal',
        following
          ? 'text-infinity-warning hover:text-infinity-warning/80'
          : 'text-infinity-text-muted hover:text-infinity-text-secondary',
      )}
    >
      <Star className="size-4" fill={following ? 'currentColor' : 'none'} aria-hidden="true" />
    </button>
  )
}
