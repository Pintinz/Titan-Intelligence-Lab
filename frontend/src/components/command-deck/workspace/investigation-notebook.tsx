import { useEffect, useState } from 'react'
import { X, Printer, Eraser } from 'lucide-react'
import { CDButton } from '../primitives/button'
import { CDLabel } from '../primitives/panel'
import { IntelligenceCompleteness, type CompletenessItem } from './intelligence-completeness'
import { latestByMarket } from './workspace-tabs'
import type { WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'
import type { PredictionMarketDto, PredictionSummaryDto } from '@/lib/api/types'

function notesKey(entity: WorkspaceEntity) {
  return `titaniq.workspace.notes.${entity.kind}.${entity.id}`
}

/**
 * InvestigationNotebook — a client-only aggregation view of the current investigation (Mission
 * Brief data, generated predictions, timeline, completeness, and free-text Notes), printable via
 * the browser's native print-to-PDF rather than a bundled PDF renderer (no new dependency —
 * see the shaped brief's resolved open decision). Notes persist per-entity to localStorage; there
 * is no backend notebook endpoint, so nothing here is shared or synced across devices.
 */
export function InvestigationNotebook({ entity, history, markets, completeness, onClose, onClearInvestigation }: {
  entity: WorkspaceEntity
  history: PredictionSummaryDto[]
  markets: PredictionMarketDto[]
  completeness: CompletenessItem[]
  onClose: () => void
  onClearInvestigation: () => void
}) {
  const [notes, setNotes] = useState('')

  useEffect(() => {
    try {
      setNotes(localStorage.getItem(notesKey(entity)) ?? '')
    } catch {
      setNotes('')
    }
  }, [entity])

  function handleNotesChange(value: string) {
    setNotes(value)
    try {
      localStorage.setItem(notesKey(entity), value)
    } catch {
      // localStorage unavailable — notes stay in memory for this view only.
    }
  }

  const latest = latestByMarket(history)
  const marketRows = markets
    .map((m) => ({ market: m, prediction: latest.get(m.id) }))
    .filter((row) => row.prediction)

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:p-8" onClick={onClose}>
      <div
        className="w-full max-w-2xl rounded-[var(--cd-radius-xl)] border p-6"
        style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between gap-3 print:hidden">
          <CDLabel>Investigation Notebook</CDLabel>
          <div className="flex items-center gap-2">
            <CDButton variant="secondary" size="sm" onClick={() => window.print()} icon={<Printer className="size-3.5" aria-hidden="true" />}>
              Export PDF
            </CDButton>
            <button
              type="button"
              onClick={() => {
                onClearInvestigation()
                onClose()
              }}
              className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] px-3 py-1.5 font-[var(--cd-font-body)] text-[12px] font-medium"
              style={{ color: 'var(--cd-negative)' }}
            >
              <Eraser className="size-3.5" aria-hidden="true" />
              Clear Investigation
            </button>
            <button type="button" onClick={onClose} aria-label="Close notebook" className="rounded-[var(--cd-radius-sm)] p-1.5" style={{ color: 'var(--cd-text-muted)' }}>
              <X className="size-4" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div id="investigation-notebook-print" className="space-y-5">
          <div>
            <p className="font-[var(--cd-font-telemetry)] text-[10px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              TitanIQ Investigation
            </p>
            <h2 className="mt-1 font-[var(--cd-font-display)] text-[20px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
              {entity.label}
            </h2>
            {entity.meta && <p className="mt-0.5 font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-muted)' }}>{entity.meta}</p>}
            <p className="mt-1 font-[var(--cd-font-tabular)] text-[10.5px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
              Generated {new Date().toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
            </p>
          </div>

          <IntelligenceCompleteness items={completeness} />

          <div>
            <CDLabel>Predictions</CDLabel>
            {marketRows.length === 0 ? (
              <p className="mt-2 font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
                No predictions generated yet.
              </p>
            ) : (
              <ul className="mt-2 space-y-1.5">
                {marketRows.map(({ market, prediction }) => (
                  <li key={market.id} className="flex items-center justify-between font-[var(--cd-font-body)] text-[12.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    <span>{market.name}</span>
                    <span className="font-[var(--cd-font-tabular)] tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
                      {String(prediction!.value)} · {(prediction!.probability * 100).toFixed(1)}% · {Math.round(prediction!.confidence_composite * 100)}% confidence
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <CDLabel>Notes</CDLabel>
            <textarea
              value={notes}
              onChange={(e) => handleNotesChange(e.target.value)}
              placeholder="Add your own notes on this investigation — saved on this device only."
              rows={4}
              className="mt-2 w-full resize-y rounded-[var(--cd-radius-md)] border p-3 font-[var(--cd-font-body)] text-[12.5px] outline-none print:border-none"
              style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-2)', color: 'var(--cd-text-primary)' }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
