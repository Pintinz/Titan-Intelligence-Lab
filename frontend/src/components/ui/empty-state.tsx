import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function EmptyState({
  title,
  description,
  icon: Icon,
  action,
  variant = 'default',
}: {
  title: string
  description?: string
  icon?: LucideIcon
  action?: ReactNode
  variant?: 'default' | 'minimal'
}) {
  return (
    <div className={cn(
      'flex flex-col items-center gap-4 px-6 py-16 text-center',
      variant === 'minimal' && 'py-8 gap-2',
    )}>
      {Icon && (
        <div className={cn(
          'flex items-center justify-center rounded-full bg-gradient-to-br from-accent-primary-muted to-bg-secondary transition-transform duration-300 hover:scale-110',
          variant === 'default' && 'size-12',
          variant === 'minimal' && 'size-8',
        )}>
          <Icon
            className={cn(
              'text-accent-primary',
              variant === 'default' && 'size-5',
              variant === 'minimal' && 'size-4',
            )}
            aria-hidden="true"
          />
        </div>
      )}
      <div className="space-y-2">
        <p className={cn(
          'font-display font-semibold text-text-primary',
          variant === 'default' && 'text-base',
          variant === 'minimal' && 'text-sm',
        )}>
          {title}
        </p>
        {description && (
          <p className={cn(
            'text-text-secondary',
            variant === 'default' && 'max-w-sm text-sm',
            variant === 'minimal' && 'max-w-xs text-xs',
          )}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}
