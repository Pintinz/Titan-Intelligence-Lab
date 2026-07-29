import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export function Tag({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border border-border-default px-2 py-0.5 text-[11px] text-text-secondary',
        className,
      )}
      {...props}
    />
  )
}
