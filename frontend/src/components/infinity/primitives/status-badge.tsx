import { cn } from '@/lib/cn'

export type SettingStatus = 'available' | 'coming-soon' | 'managed-elsewhere' | 'not-configurable'

const STATUS_CONFIG: Record<SettingStatus, { label: string; dotColor: string; textColor: string }> = {
  available: { label: 'Available', dotColor: 'var(--infinity-success)', textColor: 'var(--infinity-success)' },
  'coming-soon': { label: 'Coming soon', dotColor: 'var(--infinity-warning)', textColor: 'var(--infinity-warning)' },
  'managed-elsewhere': { label: 'Managed elsewhere', dotColor: 'var(--infinity-signal)', textColor: 'var(--infinity-signal)' },
  'not-configurable': { label: 'Not configurable', dotColor: 'var(--infinity-text-muted)', textColor: 'var(--infinity-text-muted)' },
}

/**
 * The one status vocabulary every settings row uses instead of a repeated "Not available yet" —
 * distinguishes a planned feature (coming soon) from a real control that just lives on another
 * TitanIQ page (managed elsewhere) from current, fixed platform behavior (not configurable).
 * Never red: red is reserved for genuine problems, not unavailable functionality.
 */
export function StatusBadge({ status, className }: { status: SettingStatus; className?: string }) {
  const config = STATUS_CONFIG[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-infinity-border-default px-2 py-0.5 font-infinity-mono text-[9.5px] font-medium uppercase tracking-[0.06em]',
        className,
      )}
      style={{ color: config.textColor }}
    >
      <span className="size-1.5 shrink-0 rounded-full" style={{ backgroundColor: config.dotColor }} aria-hidden="true" />
      {config.label}
    </span>
  )
}
