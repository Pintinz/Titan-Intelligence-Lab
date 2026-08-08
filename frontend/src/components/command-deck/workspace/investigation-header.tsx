import type { ReactNode } from 'react'
import { Star, Share2, Download, Save, Sparkles } from 'lucide-react'
import { CDStatusDot } from '../primitives/status'
import type { WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'

const KIND_LABEL: Record<WorkspaceEntity['kind'], string> = {
  fixture: 'Match',
  team: 'Team',
  competition: 'Competition',
  player: 'Player',
}

/**
 * InvestigationHeader — persistent command header for whatever is currently focused. Field set
 * generalizes from the brief's fixture-shaped example to every focusable kind: a team/competition/
 * player focus shows its own real meta line instead of fixture-only fields (kickoff/AI-ready only
 * apply to a fixture). Share extends the existing `?pin_type=&pin_id=` deep-link scheme already
 * used for cross-page linking — copies a URL, not a fabricated "share" backend feature.
 */
export function InvestigationHeader({
  entity,
  isPinned,
  onTogglePin,
  aiReady,
  generatedCount,
  totalMarkets,
  lastUpdated,
  onShare,
  onExport,
  onSaveSession,
}: {
  entity: WorkspaceEntity
  isPinned: boolean
  onTogglePin: () => void
  aiReady?: boolean
  generatedCount?: number
  totalMarkets?: number
  lastUpdated?: string | null
  onShare: () => void
  onExport: () => void
  onSaveSession: () => void
}) {
  const showCoverage = entity.kind === 'fixture' && typeof generatedCount === 'number' && typeof totalMarkets === 'number'

  return (
    <div
      className="sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-[var(--cd-radius-lg)] border px-4 py-3 backdrop-blur-md"
      style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-1) 88%, transparent)' }}
    >
      <div className="flex min-w-0 items-center gap-3">
        {entity.logoUrl && <img src={entity.logoUrl} alt="" className="size-8 shrink-0 object-contain" loading="lazy" />}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-[var(--cd-font-telemetry)] text-[10px] font-semibold uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
              {KIND_LABEL[entity.kind]}
            </span>
            {entity.meta && (
              <span className="truncate font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-muted)' }}>
                {entity.meta}
              </span>
            )}
          </div>
          <p className="truncate font-[var(--cd-font-display)] text-[15px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
            {entity.label}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        {entity.kind === 'fixture' && typeof aiReady === 'boolean' && (
          <CDStatusDot label={aiReady ? 'AI ready' : 'Coverage building'} tone={aiReady ? 'ready' : 'idle'} />
        )}
        {showCoverage && (
          <span className="flex items-center gap-1.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-secondary)' }}>
            <Sparkles className="size-3" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
            {generatedCount}/{totalMarkets} generated
          </span>
        )}
        {lastUpdated && (
          <span className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
            Updated {new Date(lastUpdated).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
          </span>
        )}

        <div className="flex items-center gap-1">
          <HeaderIconButton label={isPinned ? 'Unpin' : 'Pin'} active={isPinned} onClick={onTogglePin}>
            <Star className="size-3.5" fill={isPinned ? 'currentColor' : 'none'} aria-hidden="true" />
          </HeaderIconButton>
          <HeaderIconButton label="Share" onClick={onShare}>
            <Share2 className="size-3.5" aria-hidden="true" />
          </HeaderIconButton>
          <HeaderIconButton label="Export report" onClick={onExport}>
            <Download className="size-3.5" aria-hidden="true" />
          </HeaderIconButton>
          <HeaderIconButton label="Save session" onClick={onSaveSession}>
            <Save className="size-3.5" aria-hidden="true" />
          </HeaderIconButton>
        </div>
      </div>
    </div>
  )
}

function HeaderIconButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string
  active?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      aria-pressed={active}
      className="rounded-[var(--cd-radius-sm)] p-1.5 transition-colors duration-[var(--cd-motion-snap)]"
      style={{ color: active ? 'var(--cd-accent)' : 'var(--cd-text-muted)' }}
    >
      {children}
    </button>
  )
}
