import { useEffect, useState, type ReactNode } from 'react'
import { ArrowUp, X, Paperclip, Microscope, Waypoints } from 'lucide-react'
import type { CanvasTab } from './workspace-tabs'
import type { EntityKind, WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'

interface QuickPrompt {
  label: string
  run: (caps: ComposerCapabilities) => void
}

export interface ComposerCapabilities {
  hasFocusedPrediction: boolean
  onSwitchTab: (tab: CanvasTab) => void
  onOpenEvidence: () => void
  onOpenGraph: () => void
}

function promptsFor(kind: EntityKind, hasFocusedPrediction: boolean): QuickPrompt[] {
  const base: Record<EntityKind, QuickPrompt[]> = {
    fixture: [
      { label: 'Analyze this match', run: (c) => c.onSwitchTab('mission-brief') },
      { label: 'Why this verdict?', run: (c) => (c.hasFocusedPrediction ? c.onOpenEvidence() : c.onSwitchTab('predictions')) },
      { label: 'Show prediction evidence', run: (c) => (c.hasFocusedPrediction ? c.onOpenEvidence() : c.onSwitchTab('predictions')) },
      { label: 'Compare both teams', run: (c) => c.onSwitchTab('comparison') },
      { label: 'Show prediction history', run: (c) => c.onSwitchTab('timeline') },
      { label: 'Explore related fixtures', run: (c) => c.onSwitchTab('related') },
    ],
    team: [
      { label: 'Analyze recent form', run: (c) => c.onSwitchTab('mission-brief') },
      { label: 'Show prediction history', run: (c) => c.onSwitchTab('timeline') },
      { label: 'Explore connected players', run: (c) => c.onOpenGraph() },
      { label: 'Compare with another team', run: (c) => c.onSwitchTab('comparison') },
    ],
    competition: [
      { label: 'Show connected teams', run: (c) => c.onOpenGraph() },
      { label: 'Show prediction history', run: (c) => c.onSwitchTab('timeline') },
    ],
    player: [
      { label: 'Show connected team', run: (c) => c.onOpenGraph() },
    ],
  }
  const list = [...base[kind]]
  if (hasFocusedPrediction) {
    list.unshift(
      { label: 'Why this prediction?', run: (c) => c.onOpenEvidence() },
      { label: 'Show confidence breakdown', run: (c) => c.onOpenEvidence() },
      { label: 'Show probability distribution', run: (c) => c.onOpenEvidence() },
    )
  }
  return list.slice(0, 6)
}

/** Deterministic, honest keyword routing — no NLU backend exists and none is fabricated here.
 * Every match resolves to a real Canvas state change; an unmatched question surfaces one inline
 * notice, never a fabricated answer or a chat-style reply. */
function routeQuery(text: string, caps: ComposerCapabilities): boolean {
  const q = text.toLowerCase()
  const openEvidenceOrPredictions = () => (caps.hasFocusedPrediction ? caps.onOpenEvidence() : caps.onSwitchTab('predictions'))

  if (/why|believe|reason/.test(q) || /evidence|feature|driver|signal/.test(q)) {
    openEvidenceOrPredictions()
    return true
  }
  if (/confiden|probabilit|distribution/.test(q)) {
    caps.hasFocusedPrediction ? caps.onOpenEvidence() : caps.onSwitchTab('insights')
    return true
  }
  if (/compare/.test(q)) {
    caps.onSwitchTab('comparison')
    return true
  }
  if (/histor|chang|timeline|evolv|updat/.test(q)) {
    caps.onSwitchTab('timeline')
    return true
  }
  if (/graph|connect|relationship|player|manager/.test(q)) {
    caps.onOpenGraph()
    return true
  }
  if (/related|similar/.test(q)) {
    caps.onSwitchTab('related')
    return true
  }
  if (/form|analy[sz]e|brief|summary|status/.test(q)) {
    caps.onSwitchTab('mission-brief')
    return true
  }
  return false
}

/**
 * WorkspaceComposer — the mandatory "Ask TitanIQ" input. Interaction quality inspired by Claude
 * (large input, attach chip, quick suggestions), but every question resolves into a structured
 * Canvas state change — never a chat transcript, never a fabricated NLU answer. The context chip
 * is a local preview of what's currently focused; dismissing it only hides the chip for this
 * composer (the routing logic below doesn't actually depend on it — there's no backend NLU
 * consuming "context" as a prompt parameter, only real deterministic tab/panel switches).
 */
export function WorkspaceComposer({ focused, capabilities }: { focused: WorkspaceEntity | null; capabilities: ComposerCapabilities }) {
  const [value, setValue] = useState('')
  const [contextDismissed, setContextDismissed] = useState(false)
  const [unmatchedNotice, setUnmatchedNotice] = useState(false)

  useEffect(() => setContextDismissed(false), [focused?.kind, focused?.id])

  function submit() {
    const text = value.trim()
    if (!text) return
    const matched = routeQuery(text, capabilities)
    setUnmatchedNotice(!matched)
    setValue('')
  }

  const prompts = focused ? promptsFor(focused.kind, capabilities.hasFocusedPrediction) : []

  return (
    <div className="rounded-[var(--cd-radius-lg)] border p-3.5" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' }}>
      {focused && !contextDismissed && (
        <div className="mb-2.5 flex items-center gap-1.5">
          <span
            className="inline-flex items-center gap-1.5 rounded-full py-1 pl-2.5 pr-1.5 font-[var(--cd-font-body)] text-[11.5px] font-medium"
            style={{ backgroundColor: 'var(--cd-accent-muted)', color: 'var(--cd-accent)' }}
          >
            {focused.label}
            <button type="button" onClick={() => setContextDismissed(true)} aria-label="Remove context" className="rounded-full p-0.5 hover:opacity-70">
              <X className="size-3" aria-hidden="true" />
            </button>
          </span>
        </div>
      )}

      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        rows={2}
        placeholder="Ask about this match, prediction, evidence, or connected intelligence…"
        className="w-full resize-none bg-transparent font-[var(--cd-font-body)] text-[14px] outline-none placeholder:text-[var(--cd-text-muted)]"
        style={{ color: 'var(--cd-text-primary)' }}
      />

      <div className="mt-2 flex items-center justify-between gap-2 border-t pt-2.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <div className="flex items-center gap-1">
          <ComposerChipButton icon={<Paperclip className="size-3.5" aria-hidden="true" />} label="Context" onClick={() => capabilities.onSwitchTab('mission-brief')} />
          <ComposerChipButton icon={<Microscope className="size-3.5" aria-hidden="true" />} label="Evidence" onClick={() => (capabilities.hasFocusedPrediction ? capabilities.onOpenEvidence() : capabilities.onSwitchTab('predictions'))} />
          <ComposerChipButton icon={<Waypoints className="size-3.5" aria-hidden="true" />} label="Graph" onClick={capabilities.onOpenGraph} />
        </div>
        <button
          type="button"
          onClick={submit}
          disabled={!value.trim()}
          aria-label="Ask TitanIQ"
          className="flex size-7 shrink-0 items-center justify-center rounded-full transition-opacity disabled:opacity-30"
          style={{ backgroundColor: 'var(--cd-accent)', color: 'var(--cd-text-inverse)' }}
        >
          <ArrowUp className="size-3.5" aria-hidden="true" />
        </button>
      </div>

      {prompts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {prompts.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => p.run(capabilities)}
              className="rounded-full border px-2.5 py-1 font-[var(--cd-font-body)] text-[11.5px] font-medium transition-colors duration-[var(--cd-motion-snap)]"
              style={{ borderColor: 'var(--cd-border-default)', color: 'var(--cd-text-secondary)' }}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {unmatchedNotice && (
        <p className="mt-2.5 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
          TitanIQ can investigate predictions, evidence, comparisons, timelines, and relationships for what's focused — try one of the suggestions above.
        </p>
      )}
    </div>
  )
}

function ComposerChipButton({ icon, label, onClick }: { icon: ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-[var(--cd-radius-sm)] px-2 py-1 font-[var(--cd-font-body)] text-[11.5px]"
      style={{ color: 'var(--cd-text-muted)' }}
    >
      {icon}
      {label}
    </button>
  )
}
