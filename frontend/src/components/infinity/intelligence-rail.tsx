import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/cn'

export type RailItemStatus = 'live' | 'upcoming' | 'completed' | 'high-confidence' | 'learning' | 'alert' | 'breaking'

export interface RailItem {
  id: string
  icon: LucideIcon
  label: string
  meta: string
  status: RailItemStatus
}

const STATUS_TONE: Record<RailItemStatus, string> = {
  live: 'var(--infinity-live)',
  upcoming: 'var(--infinity-text-muted)',
  completed: 'var(--infinity-success)',
  'high-confidence': 'var(--infinity-confidence-high)',
  learning: 'var(--infinity-domain-learning)',
  alert: 'var(--infinity-warning)',
  breaking: 'var(--infinity-domain-news)',
}

/**
 * Intelligence Rail 2.0 — a horizontal scroll of compact evidence chips, each with a
 * status-colored left edge (not a full-tint background — the "subtle motion, elegant
 * glow, never distracting" rule from the brief). `live` items get a slow pulse on their
 * edge marker only, everything else stays static.
 */
export function InfinityIntelligenceRail({ items }: { items: RailItem[] }) {
  return (
    <div role="list" aria-label="Intelligence rail" className="flex gap-2 overflow-x-auto pb-1">
      {items.map((item) => {
        const tone = STATUS_TONE[item.status]
        const Icon = item.icon
        return (
          <div
            key={item.id}
            role="listitem"
            className="flex shrink-0 items-center gap-2.5 border-l-2 bg-infinity-ground-1 py-2 pl-3 pr-4"
            style={{ borderColor: tone }}
          >
            <span
              className={cn('size-1.5 shrink-0 rounded-full', item.status === 'live' && 'animate-pulse')}
              style={{ backgroundColor: tone }}
              aria-hidden="true"
            />
            <Icon className="size-3.5 shrink-0" style={{ color: tone }} aria-hidden="true" />
            <div className="min-w-0">
              <p className="truncate font-infinity-body text-[12px] font-medium text-infinity-text-primary">{item.label}</p>
              <p className="truncate font-infinity-mono text-[10px] text-infinity-text-muted">{item.meta}</p>
            </div>
          </div>
        )
      })}
    </div>
  )
}
