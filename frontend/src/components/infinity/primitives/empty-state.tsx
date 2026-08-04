import type { LucideIcon } from 'lucide-react'
import { InfinityButton } from './button'

/**
 * Never a generic illustration — every Infinity empty state explains what's missing,
 * why, and what to do about it, framed the way a broadcast graphic explains "no data
 * available yet" during a pre-match wait rather than a dead-end icon.
 */
export function InfinityEmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description: string
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="flex flex-col items-center gap-3 border border-dashed border-infinity-border-default px-6 py-14 text-center">
      <div className="flex size-10 items-center justify-center rounded-full border border-infinity-border-default bg-infinity-ground-2">
        <Icon className="size-4 text-infinity-text-muted" aria-hidden="true" />
      </div>
      <div className="space-y-1.5">
        <p className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">{title}</p>
        <p className="max-w-sm font-infinity-body text-[13px] text-infinity-text-secondary">{description}</p>
      </div>
      {action && (
        <InfinityButton size="sm" variant="outline" onClick={action.onClick} className="mt-1">
          {action.label}
        </InfinityButton>
      )}
    </div>
  )
}
