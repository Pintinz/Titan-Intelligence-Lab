import { forwardRef, type InputHTMLAttributes } from 'react'
import { Search } from 'lucide-react'
import { cn } from '@/lib/cn'

export const InfinityInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'h-9 w-full rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 px-3',
        'font-infinity-body text-[13px] text-infinity-text-primary placeholder:text-infinity-text-muted',
        'transition-colors duration-100 focus:border-infinity-signal focus:outline-none focus:ring-1 focus:ring-infinity-signal',
        className,
      )}
      {...props}
    />
  ),
)
InfinityInput.displayName = 'InfinityInput'

/** The review-technology search field — a hairline-bordered field with a persistent
 * scan-icon, not a rounded pill search box. Used by the nav Search component and
 * anywhere else a filter/search affordance appears. */
export const InfinitySearchInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-infinity-text-muted" aria-hidden="true" />
      <input
        ref={ref}
        className={cn(
          'h-9 w-full rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 pl-8 pr-3',
          'font-infinity-body text-[13px] text-infinity-text-primary placeholder:text-infinity-text-muted',
          'transition-colors duration-100 focus:border-infinity-signal focus:outline-none focus:ring-1 focus:ring-infinity-signal',
          className,
        )}
        {...props}
      />
    </div>
  ),
)
InfinitySearchInput.displayName = 'InfinitySearchInput'
