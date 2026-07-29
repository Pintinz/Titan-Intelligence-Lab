import { cn } from '@/lib/cn'

export interface ProgressProps {
  value: number
  max?: number
  className?: string
  label?: string
}

export function Progress({ value, max = 100, className, label }: ProgressProps) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-label={label}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-bg-secondary', className)}
    >
      <div
        className="h-full rounded-full bg-accent-primary transition-[width] duration-300 ease-[var(--motion-easing-standard)]"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
