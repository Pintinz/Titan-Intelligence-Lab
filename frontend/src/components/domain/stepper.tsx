import { Check } from 'lucide-react'
import { cn } from '@/lib/cn'

export interface Step {
  id: string
  label: string
}

export function Stepper({ steps, currentStepId, className }: { steps: Step[]; currentStepId: string; className?: string }) {
  const currentIndex = steps.findIndex((s) => s.id === currentStepId)

  return (
    <ol className={cn('flex items-center', className)}>
      {steps.map((step, index) => {
        const isComplete = index < currentIndex
        const isCurrent = index === currentIndex
        return (
          <li key={step.id} className="flex flex-1 items-center last:flex-none">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium',
                  isComplete && 'bg-accent-primary text-text-inverse',
                  isCurrent && 'border-2 border-accent-primary text-accent-primary',
                  !isComplete && !isCurrent && 'border border-border-default text-text-muted',
                )}
                aria-current={isCurrent ? 'step' : undefined}
              >
                {isComplete ? <Check className="h-3.5 w-3.5" /> : index + 1}
              </span>
              <span className={cn('text-sm', isCurrent ? 'font-medium text-text-primary' : 'text-text-secondary')}>
                {step.label}
              </span>
            </div>
            {index < steps.length - 1 && (
              <div className={cn('mx-3 h-px flex-1', isComplete ? 'bg-accent-primary' : 'bg-border-default')} />
            )}
          </li>
        )
      })}
    </ol>
  )
}
