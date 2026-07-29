import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

export function EmptyState({
  title,
  description,
  icon: Icon,
  action,
}: {
  title: string
  description?: string
  icon?: LucideIcon
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      {Icon && (
        <div className="flex size-10 items-center justify-center rounded-full bg-bg-secondary">
          <Icon className="size-4 text-text-muted" aria-hidden="true" />
        </div>
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium text-text-primary">{title}</p>
        {description && <p className="max-w-xs text-sm text-text-secondary">{description}</p>}
      </div>
      {action}
    </div>
  )
}
