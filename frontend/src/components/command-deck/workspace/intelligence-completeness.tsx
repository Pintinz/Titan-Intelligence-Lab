import { CircleCheck, CircleDashed, CircleSlash } from 'lucide-react'
import { CDPanel, CDLabel } from '../primitives/panel'

export type CompletenessState = 'complete' | 'pending' | 'unavailable'

export interface CompletenessItem {
  key: string
  label: string
  state: CompletenessState
}

const STATE_META: Record<CompletenessState, { icon: typeof CircleCheck; color: string; text: string }> = {
  complete: { icon: CircleCheck, color: 'var(--cd-positive)', text: 'Complete' },
  pending: { icon: CircleDashed, color: 'var(--cd-text-muted)', text: 'Pending' },
  unavailable: { icon: CircleSlash, color: 'var(--cd-text-muted)', text: 'Not available yet' },
}

/**
 * IntelligenceCompleteness — real per-item completeness only. Lineups and Officials are always
 * `unavailable`, never `pending`: both are Knowledge Graph node types that exist only in the
 * ontology with no population writer anywhere in the backend (confirmed against
 * `value_objects.py`), so nothing will ever move them to Complete without new backend work —
 * "Pending" would wrongly imply that's already in motion.
 */
export function IntelligenceCompleteness({ items }: { items: CompletenessItem[] }) {
  const completeCount = items.filter((i) => i.state === 'complete').length
  const percent = items.length > 0 ? Math.round((completeCount / items.length) * 100) : 0

  return (
    <CDPanel padding="tight">
      <div className="flex items-center justify-between gap-2">
        <CDLabel>Intelligence completeness</CDLabel>
        <span className="font-[var(--cd-font-tabular)] text-[13px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
          {percent}%
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }}>
        <div
          className="h-full rounded-full transition-[width] duration-[var(--cd-motion-deliberate)] ease-out"
          style={{ width: `${percent}%`, backgroundColor: 'var(--cd-accent)' }}
        />
      </div>
      <ul className="mt-3 space-y-1.5">
        {items.map((item) => {
          const meta = STATE_META[item.state]
          const Icon = meta.icon
          return (
            <li key={item.key} className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-secondary)' }}>
                <Icon className="size-3.5 shrink-0" style={{ color: meta.color }} aria-hidden="true" />
                {item.label}
              </span>
              <span className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.05em]" style={{ color: meta.color }}>
                {meta.text}
              </span>
            </li>
          )
        })}
      </ul>
    </CDPanel>
  )
}
