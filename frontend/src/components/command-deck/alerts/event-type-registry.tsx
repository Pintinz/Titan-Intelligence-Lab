import { Check, Circle } from 'lucide-react'

const ACTIVE_TYPES = ['Kickoff', 'Final', 'Prediction changes']

const NOT_AVAILABLE = [
  { label: 'Goal', description: 'Live match-event ingestion required.' },
  { label: 'Lineups', description: 'No lineup provider integration currently available.' },
  { label: 'Injuries', description: 'No injury data source is currently connected.' },
  { label: 'Breaking News', description: 'No impact-scored news trigger currently exists.' },
]

/**
 * EventTypeRegistry — a capability list, not a warning list: what actually fires today vs what's
 * planned but has no real data trigger wired in. Never rendered inside the alert timeline, never
 * carries a notification badge — the shaped brief is explicit these must never look like active
 * alerts.
 */
export function EventTypeRegistry() {
  return (
    <div>
      <p className="font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-accent)' }}>
        Active
      </p>
      <ul className="mt-2 flex flex-wrap gap-2">
        {ACTIVE_TYPES.map((label) => (
          <li
            key={label}
            className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-sm)] px-2.5 py-1 font-[var(--cd-font-body)] text-[12px]"
            style={{ backgroundColor: 'var(--cd-surface-2)', border: '1px solid var(--cd-border-hairline)', color: 'var(--cd-text-secondary)' }}
          >
            <Check className="size-3" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
            {label}
          </li>
        ))}
      </ul>

      <p className="mt-5 font-[var(--cd-font-telemetry)] text-[9.5px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
        Not available
      </p>
      <ul className="mt-2 divide-y" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {NOT_AVAILABLE.map((item) => (
          <li key={item.label} className="flex items-start justify-between gap-4 py-2.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
            <div className="min-w-0">
              <p className="flex items-center gap-1.5 font-[var(--cd-font-body)] text-[12.5px] font-medium" style={{ color: 'var(--cd-text-secondary)' }}>
                <Circle className="size-2.5 shrink-0" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
                {item.label}
              </p>
              <p className="mt-0.5 font-[var(--cd-font-body)] text-[11.5px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
                {item.description}
              </p>
            </div>
            <span
              className="shrink-0 rounded-[var(--cd-radius-sm)] px-1.5 py-0.5 font-[var(--cd-font-telemetry)] text-[9px] font-medium uppercase tracking-[0.05em]"
              style={{ color: 'var(--cd-text-muted)', border: '1px solid var(--cd-border-default)' }}
            >
              Not available
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
