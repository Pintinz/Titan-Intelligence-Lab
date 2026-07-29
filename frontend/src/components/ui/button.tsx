import type { ButtonHTMLAttributes } from 'react'
import { Slot, Slottable } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import { cn } from '@/lib/cn'

export const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors ' +
    'disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 ' +
    'focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary',
  {
    variants: {
      variant: {
        primary: 'bg-accent-primary text-text-inverse hover:bg-accent-primary-hover',
        secondary:
          'bg-bg-elevated text-text-primary border border-border-default hover:border-border-strong',
        ghost: 'text-text-secondary hover:bg-bg-elevated hover:text-text-primary',
        danger: 'bg-danger text-text-inverse hover:opacity-90',
        link: 'text-accent-primary underline-offset-4 hover:underline',
      },
      size: {
        sm: 'h-8 px-3 text-sm',
        md: 'h-9 px-4 text-sm',
        lg: 'h-11 px-6 text-base',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
  loading?: boolean
}

export function Button({ className, variant, size, asChild, loading, disabled, children, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : 'button'
  return (
    <Comp className={cn(buttonVariants({ variant, size }), className)} disabled={disabled || loading} {...props}>
      {/* Slot (asChild) requires exactly one element child — Slottable marks which child receives
          the merged props/ref when a sibling (the loading spinner) is also present. */}
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      <Slottable>{children}</Slottable>
    </Comp>
  )
}
