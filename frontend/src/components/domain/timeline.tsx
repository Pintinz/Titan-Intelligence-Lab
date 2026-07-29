import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export interface TimelineEntry {
  id: string
  timestamp: string
  title: ReactNode
  description?: ReactNode
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info'
}

const TONE_DOT_CLASS: Record<NonNullable<TimelineEntry['tone']>, string> = {
  neutral: 'bg-text-muted',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
}

export function Timeline({ entries, className }: { entries: TimelineEntry[]; className?: string }) {
  return (
    <ol className={cn('relative flex flex-col gap-6 border-l border-border-subtle pl-6', className)}>
      {entries.map((entry) => (
        <li key={entry.id} className="relative">
          <span
            className={cn('absolute -left-[29px] top-1 h-2.5 w-2.5 rounded-full ring-4 ring-bg-primary', TONE_DOT_CLASS[entry.tone ?? 'neutral'])}
            aria-hidden="true"
          />
          <p className="text-xs text-text-muted">{new Date(entry.timestamp).toLocaleString()}</p>
          <p className="mt-0.5 text-sm font-medium text-text-primary">{entry.title}</p>
          {entry.description && <div className="mt-1 text-sm text-text-secondary">{entry.description}</div>}
        </li>
      ))}
    </ol>
  )
}
