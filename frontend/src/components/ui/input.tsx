import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-9 w-full rounded-md border border-border-default bg-bg-primary px-3 text-sm text-text-primary',
        'placeholder:text-text-muted transition-colors duration-[var(--motion-duration-fast)]',
        'focus-visible:border-accent-primary focus-visible:outline-none',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'aria-invalid:border-danger',
        className,
      )}
      {...props}
    />
  ),
)
Input.displayName = 'Input'
