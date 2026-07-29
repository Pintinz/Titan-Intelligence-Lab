import type { ComponentProps } from 'react'
import * as PopoverPrimitive from '@radix-ui/react-popover'
import { cn } from '@/lib/cn'

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export const PopoverAnchor = PopoverPrimitive.Anchor

export function PopoverContent({ className, align = 'center', sideOffset = 6, ...props }: ComponentProps<typeof PopoverPrimitive.Content>) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        sideOffset={sideOffset}
        className={cn(
          'z-50 w-72 rounded-lg border border-border-default bg-bg-elevated p-4 shadow-[var(--shadow-elevation-2)] focus-visible:outline-none',
          'data-[state=open]:animate-[popover-content-in_var(--motion-duration-fast)_var(--motion-easing-decelerate)]',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
}
