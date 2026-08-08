import type { ReactNode } from 'react'
import { Sparkles, GitCompare, Waypoints, Download, Save, ExternalLink } from 'lucide-react'

interface ActionBarProps {
  onGenerate: () => void
  onCompare: () => void
  onKnowledgeGraph: () => void
  onExportReport: () => void
  onSaveSession: () => void
  onOpenMatch: () => void
  canGenerate: boolean
  canOpenMatch: boolean
}

/**
 * WorkspaceActionBar — persistent bottom bar, always present (not conditionally mounted only once
 * something is focused) so the workspace always reads as an instrument panel rather than a page
 * that only becomes real after a search. Actions disable rather than disappear when their target
 * doesn't apply yet (nothing focused, or a non-fixture focus for fixture-only actions).
 */
export function WorkspaceActionBar({
  onGenerate,
  onCompare,
  onKnowledgeGraph,
  onExportReport,
  onSaveSession,
  onOpenMatch,
  canGenerate,
  canOpenMatch,
}: ActionBarProps) {
  return (
    <div
      className="sticky bottom-0 z-10 -mx-4 flex flex-wrap items-center justify-center gap-1.5 border-t px-4 py-3 backdrop-blur-md sm:justify-start"
      style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-1) 90%, transparent)' }}
    >
      <ActionButton icon={<Sparkles className="size-3.5" aria-hidden="true" />} label="Generate Intelligence" onClick={onGenerate} disabled={!canGenerate} primary />
      <ActionButton icon={<GitCompare className="size-3.5" aria-hidden="true" />} label="Compare Teams" onClick={onCompare} />
      <ActionButton icon={<Waypoints className="size-3.5" aria-hidden="true" />} label="Knowledge Graph" onClick={onKnowledgeGraph} />
      <ActionButton icon={<Download className="size-3.5" aria-hidden="true" />} label="Export Report" onClick={onExportReport} />
      <ActionButton icon={<Save className="size-3.5" aria-hidden="true" />} label="Save Session" onClick={onSaveSession} />
      <ActionButton icon={<ExternalLink className="size-3.5" aria-hidden="true" />} label="Open Match" onClick={onOpenMatch} disabled={!canOpenMatch} />
    </div>
  )
}

function ActionButton({ icon, label, onClick, disabled, primary }: { icon: ReactNode; label: string; onClick: () => void; disabled?: boolean; primary?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1.5 rounded-[var(--cd-radius-md)] px-3 py-2 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-snap)] disabled:cursor-not-allowed disabled:opacity-35"
      style={
        primary
          ? { backgroundImage: 'var(--cd-btn-primary-bg)', color: 'var(--cd-text-inverse)' }
          : { color: 'var(--cd-text-secondary)' }
      }
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  )
}
