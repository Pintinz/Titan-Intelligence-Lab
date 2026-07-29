import * as ToastPrimitive from '@radix-ui/react-toast'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'
import { useToastStore } from '@/stores/toast-store'
import { cn } from '@/lib/cn'

const VARIANT_ICON = {
  default: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertTriangle,
} as const

const VARIANT_CLASS = {
  default: 'border-border-default text-text-primary',
  success: 'border-success/40 text-success',
  warning: 'border-warning/40 text-warning',
  danger: 'border-danger/40 text-danger',
} as const

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts)
  const dismiss = useToastStore((s) => s.dismiss)

  return (
    <ToastPrimitive.Provider swipeDirection="right">
      {toasts.map((t) => {
        const Icon = VARIANT_ICON[t.variant]
        return (
          <ToastPrimitive.Root
            key={t.id}
            duration={5000}
            onOpenChange={(open) => {
              if (!open) dismiss(t.id)
            }}
            className={cn(
              'grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-lg border bg-bg-elevated p-4 shadow-[var(--shadow-elevation-2)]',
              VARIANT_CLASS[t.variant],
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div>
              <ToastPrimitive.Title className="text-sm font-medium text-text-primary">{t.title}</ToastPrimitive.Title>
              {t.description && (
                <ToastPrimitive.Description className="mt-0.5 text-sm text-text-secondary">
                  {t.description}
                </ToastPrimitive.Description>
              )}
            </div>
            <ToastPrimitive.Close className="rounded p-0.5 text-text-muted hover:text-text-primary" aria-label="Dismiss">
              <X className="h-3.5 w-3.5" />
            </ToastPrimitive.Close>
          </ToastPrimitive.Root>
        )
      })}
      <ToastPrimitive.Viewport className="fixed bottom-0 right-0 z-[100] flex w-full max-w-sm flex-col gap-2 p-6 outline-none" />
    </ToastPrimitive.Provider>
  )
}
