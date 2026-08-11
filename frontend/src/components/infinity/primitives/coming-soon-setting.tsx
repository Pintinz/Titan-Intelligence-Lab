import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { StatusBadge, type SettingStatus } from './status-badge'

/**
 * The one shape every not-yet-real setting renders through — a compact row, never an oversized
 * empty card, so a page full of future functionality still reads as a finished product.
 */
export function ComingSoonSetting({
  icon: Icon,
  title,
  description,
  status = 'coming-soon',
  children,
}: {
  icon: LucideIcon
  title: string
  description: string
  status?: SettingStatus
  children?: ReactNode
}) {
  return (
    <div className="flex items-start gap-3 rounded-infinity-md border border-infinity-border-default bg-infinity-ground-1 p-3.5">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-infinity-sm bg-infinity-ground-2 text-infinity-text-muted" aria-hidden="true">
        <Icon className="size-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-infinity-body text-[13px] font-medium text-infinity-text-primary">{title}</p>
          <StatusBadge status={status} />
        </div>
        <p className="text-[12.5px] leading-relaxed text-infinity-text-secondary">{description}</p>
        {children}
      </div>
    </div>
  )
}
