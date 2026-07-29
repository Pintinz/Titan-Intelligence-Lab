import * as ToastPrimitive from '@radix-ui/react-toast'
import { X } from 'lucide-react'
import { useToastStore, type ToastVariant } from '@/stores/toast-store'
import { cn } from '@/lib/cn'

const variantRail: Record<ToastVariant, string> = {
  default: 'before:bg-accent-primary',
  success: 'before:bg-success',
  warning: 'before:bg-warning',
  danger: 'before:bg-danger',
}

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {toasts.map((t) => (
        <ToastPrimitive.Root
          key={t.id}
          duration={5000}
          onOpenChange={(open) => !open && dismiss(t.id)}
          className={cn(
            'relative overflow-hidden rounded-md border border-border-default bg-bg-elevated py-3 pl-4 pr-8 shadow-[var(--shadow-elevation-3)]',
            "before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:content-['']",
            variantRail[t.variant],
            'data-[state=open]:animate-[toast-in_var(--motion-duration-base)_var(--motion-easing-decelerate)]',
          )}
        >
          <ToastPrimitive.Title className="text-sm font-medium text-text-primary">{t.title}</ToastPrimitive.Title>
          {t.description && (
            <ToastPrimitive.Description className="mt-1 text-xs text-text-secondary">
              {t.description}
            </ToastPrimitive.Description>
          )}
          <ToastPrimitive.Close
            aria-label="Dismiss notification"
            className="absolute right-2 top-2 text-text-muted hover:text-text-primary"
          >
            <X className="size-3.5" />
          </ToastPrimitive.Close>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  )
}
