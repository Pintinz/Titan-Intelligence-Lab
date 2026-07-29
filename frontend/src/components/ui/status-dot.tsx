import { cn } from '@/lib/cn'

export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

const TONE_CLASS: Record<StatusTone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  neutral: 'bg-text-muted',
}

export function StatusDot({ tone, label, className }: { tone: StatusTone; label?: string; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span className={cn('h-1.5 w-1.5 rounded-full', TONE_CLASS[tone])} aria-hidden="true" />
      {label && <span className="text-xs text-text-secondary">{label}</span>}
    </span>
  )
}
