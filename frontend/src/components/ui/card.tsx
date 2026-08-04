import { forwardRef, type HTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

/**
 * Base surface. Intelligence-bearing cards (match/prediction/model, etc.) compose this with the
 * `rail` prop — a persistent left-edge status bar (the "Intelligence Rail") that encodes
 * live/scheduled/completed state by color before any text is read.
 */
export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  rail?: 'live' | 'scheduled' | 'completed' | 'none'
}

const railColor: Record<NonNullable<CardProps['rail']>, string> = {
  live: 'before:bg-live',
  scheduled: 'before:bg-border-strong',
  completed: 'before:bg-success',
  none: 'before:bg-transparent',
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, rail = 'none', ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'relative overflow-hidden rounded-lg border border-border-default bg-bg-elevated transition-all duration-300',
        'shadow-elevation-1 hover:shadow-elevation-2',
        rail !== 'none' &&
          'pl-[19px] before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:content-[""] before:transition-opacity before:duration-300',
        railColor[rail],
        className,
      )}
      {...props}
    />
  ),
)
Card.displayName = 'Card'

export const CardHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex flex-col gap-1 p-4', className)} {...props} />
  ),
)
CardHeader.displayName = 'CardHeader'

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3
      ref={ref}
      className={cn('font-display text-base font-semibold leading-tight text-text-primary', className)}
      {...props}
    />
  ),
)
CardTitle.displayName = 'CardTitle'

export const CardDescription = forwardRef<HTMLParagraphElement, HTMLAttributes<HTMLParagraphElement>>(
  ({ className, ...props }, ref) => (
    <p ref={ref} className={cn('text-sm text-text-secondary', className)} {...props} />
  ),
)
CardDescription.displayName = 'CardDescription'

export const CardContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('p-4 pt-0', className)} {...props} />,
)
CardContent.displayName = 'CardContent'

export const CardFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn('flex items-center gap-2 border-t border-border-subtle p-4', className)} {...props} />
  ),
)
CardFooter.displayName = 'CardFooter'
