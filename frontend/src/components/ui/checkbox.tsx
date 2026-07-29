import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import { Check } from 'lucide-react'
import { forwardRef } from 'react'
import { cn } from '@/lib/cn'

export const Checkbox = forwardRef<
  React.ElementRef<typeof CheckboxPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>
>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root
    ref={ref}
    className={cn(
      'flex size-4 shrink-0 items-center justify-center rounded border border-border-default bg-bg-primary',
      'data-[state=checked]:border-accent-primary data-[state=checked]:bg-accent-primary',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-1 focus-visible:ring-offset-bg-primary',
      className,
    )}
    {...props}
  >
    <CheckboxPrimitive.Indicator className="text-bg-primary">
      <Check className="size-3" strokeWidth={3} />
    </CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
))
Checkbox.displayName = CheckboxPrimitive.Root.displayName
