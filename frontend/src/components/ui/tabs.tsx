import type { ComponentProps } from 'react'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/lib/cn'

export const Tabs = TabsPrimitive.Root

export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        'inline-flex items-center gap-1 rounded-md border border-border-default bg-bg-secondary p-1',
        className,
      )}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'rounded-[calc(var(--radius-md)-4px)] px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors',
        'hover:text-text-primary',
        'data-[state=active]:bg-bg-elevated data-[state=active]:text-text-primary data-[state=active]:shadow-[var(--shadow-elevation-1)]',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary',
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      className={cn('mt-3 focus-visible:outline-none', className)}
      {...props}
    />
  )
}
