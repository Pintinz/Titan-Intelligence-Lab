import type { ReactNode } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/cn'

export interface StatCardProps {
  label: string
  value: string | number
  icon?: ReactNode
  delta?: { value: string; direction: 'up' | 'down' | 'flat'; tone?: 'positive' | 'negative' | 'neutral' }
  className?: string
}

export function StatCard({ label, value, icon, delta, className }: StatCardProps) {
  return (
    <Card className={cn('flex flex-col gap-2 p-5', className)}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold text-text-primary">{value}</span>
        {delta && (
          <span
            className={cn(
              'flex items-center gap-0.5 text-xs font-medium',
              delta.tone === 'positive' && 'text-success',
              delta.tone === 'negative' && 'text-danger',
              (!delta.tone || delta.tone === 'neutral') && 'text-text-muted',
            )}
          >
            {delta.direction === 'up' && <ArrowUp className="h-3 w-3" />}
            {delta.direction === 'down' && <ArrowDown className="h-3 w-3" />}
            {delta.value}
          </span>
        )}
      </div>
    </Card>
  )
}
