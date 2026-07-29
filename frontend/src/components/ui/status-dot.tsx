import { cn } from '@/lib/cn'

export type StatusDotTone = 'live' | 'success' | 'warning' | 'danger' | 'neutral'

const toneClass: Record<StatusDotTone, string> = {
  live: 'bg-live',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-text-muted',
}

/** A single status pixel. `pulse` is reserved for genuinely live state, never decorative. */
export function StatusDot({
  tone = 'neutral',
  pulse = false,
  className,
}: {
  tone?: StatusDotTone
  pulse?: boolean
  className?: string
}) {
  return (
    <span className={cn('relative inline-flex size-2', className)}>
      {pulse && (
        <span
          className={cn(
            'absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:animate-none',
            toneClass[tone],
          )}
        />
      )}
      <span className={cn('relative inline-flex size-2 rounded-full', toneClass[tone])} />
    </span>
  )
}
