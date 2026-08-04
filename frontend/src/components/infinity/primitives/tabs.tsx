import * as TabsPrimitive from '@radix-ui/react-tabs'
import { cn } from '@/lib/cn'

export const InfinityTabs = TabsPrimitive.Root

/** Underline-style tabs — a signal-cyan bottom bar that slides between tabs (via
 * `layout` transition in consuming code if animated), not a filled pill selector. */
export function InfinityTabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return <TabsPrimitive.List className={cn('flex gap-5 border-b border-infinity-border-hairline', className)} {...props} />
}

export function InfinityTabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        'relative -mb-px border-b-2 border-transparent px-0.5 pb-2.5 font-infinity-body text-[13px] font-medium text-infinity-text-muted',
        'transition-colors duration-150 hover:text-infinity-text-secondary',
        'data-[state=active]:border-infinity-signal data-[state=active]:text-infinity-text-primary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal focus-visible:ring-offset-2 focus-visible:ring-offset-infinity-ground-0',
        className,
      )}
      {...props}
    />
  )
}

export const InfinityTabsContent = TabsPrimitive.Content
