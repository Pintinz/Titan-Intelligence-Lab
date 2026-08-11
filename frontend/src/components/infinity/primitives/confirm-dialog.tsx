import * as DialogPrimitive from '@radix-ui/react-dialog'
import { cn } from '@/lib/cn'
import { InfinityButton } from './button'

/**
 * Centered confirmation modal for destructive settings actions (revoke session, revoke token).
 * Built on the same Radix Dialog primitive the mobile nav and command palette already use — no
 * new dependency, no second modal system.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  destructive = true,
  onConfirm,
  isPending = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  confirmLabel?: string
  destructive?: boolean
  onConfirm: () => void
  isPending?: boolean
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay
          className={cn(
            'fixed inset-0 z-50 bg-black/60',
            'data-[state=open]:animate-[overlay-fade-in_var(--infinity-motion-base)_ease-out]',
            'data-[state=closed]:animate-[overlay-fade-out_var(--infinity-motion-base)_ease-in]',
          )}
        />
        <DialogPrimitive.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 w-[min(400px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2',
            'rounded-infinity-md border border-infinity-border-default bg-infinity-ground-1 p-5 shadow-[var(--infinity-elevation-2)]',
            'data-[state=open]:animate-[dialog-content-in_var(--infinity-motion-hold)_ease-out]',
          )}
        >
          <DialogPrimitive.Title className="font-infinity-display text-[15px] font-semibold text-infinity-text-primary">
            {title}
          </DialogPrimitive.Title>
          <DialogPrimitive.Description className="mt-1.5 text-[13px] leading-relaxed text-infinity-text-secondary">
            {description}
          </DialogPrimitive.Description>
          <div className="mt-5 flex justify-end gap-2">
            <DialogPrimitive.Close asChild>
              <InfinityButton type="button" variant="secondary" size="sm">
                Cancel
              </InfinityButton>
            </DialogPrimitive.Close>
            <InfinityButton type="button" variant={destructive ? 'danger' : 'primary'} size="sm" onClick={onConfirm} disabled={isPending}>
              {isPending ? 'Working…' : confirmLabel}
            </InfinityButton>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
