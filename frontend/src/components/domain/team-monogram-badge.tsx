import { cn } from '@/lib/cn'

/**
 * No crest/logo field exists on TeamSummaryDto/CompetitionSummaryDto (confirmed against
 * lib/api/types.ts) — this renders a deterministic initials badge (same id always produces the
 * same color/initials) instead of a fake or placeholder image.
 */
function hashToHue(id: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i++) {
    hash = (hash << 5) - hash + id.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash) % 360
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[words.length - 1][0]).toUpperCase()
}

export function TeamMonogramBadge({ id, name, size = 40, className }: { id: string; name: string; size?: number; className?: string }) {
  const hue = hashToHue(id)
  return (
    <div
      className={cn('flex shrink-0 items-center justify-center rounded-full font-display font-semibold text-text-inverse', className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        backgroundColor: `hsl(${hue} 55% 45%)`,
      }}
      aria-hidden="true"
    >
      {initials(name)}
    </div>
  )
}
