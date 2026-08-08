import { useState } from 'react'
import { X, GripVertical, History as HistoryIcon } from 'lucide-react'
import { CDLabel } from '../primitives/panel'
import type { EntityKind, WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'

const GROUP_ORDER: EntityKind[] = ['fixture', 'team', 'competition', 'player']
const GROUP_LABELS: Record<EntityKind, string> = {
  fixture: 'Matches',
  team: 'Teams',
  competition: 'Competitions',
  player: 'Players',
}

function entityKey(e: WorkspaceEntity) {
  return `${e.kind}:${e.id}`
}

/**
 * InvestigationContextRail — the renamed "Pinned" workspace. Groups pinned entities by kind
 * (only real, non-empty groups render — no fabricated "Prediction Markets"/"News" pin kinds, since
 * this workspace only ever pins entities, not individual markets or articles) and reorders within
 * a group via native HTML5 drag (no DnD library installed, and this doesn't need one). Recently
 * Opened is a flat, unordered, localStorage-backed list — not draggable, since order there is
 * chronological by definition.
 */
export function InvestigationContextRail({
  pinned,
  recentlyOpened,
  focusedKey,
  onFocus,
  onUnpin,
  onReorder,
}: {
  pinned: WorkspaceEntity[]
  recentlyOpened: WorkspaceEntity[]
  focusedKey: string | null
  onFocus: (entity: WorkspaceEntity) => void
  onUnpin: (entity: WorkspaceEntity) => void
  onReorder: (kind: EntityKind, fromIndex: number, toIndex: number) => void
}) {
  const [dragging, setDragging] = useState<{ kind: EntityKind; index: number } | null>(null)

  const groups = GROUP_ORDER.map((kind) => ({ kind, items: pinned.filter((p) => p.kind === kind) })).filter(
    (g) => g.items.length > 0,
  )
  const pinnedKeys = new Set(pinned.map(entityKey))
  const unpinnedRecent = recentlyOpened.filter((e) => !pinnedKeys.has(entityKey(e)))

  return (
    <div className="space-y-5">
      {groups.length === 0 && unpinnedRecent.length === 0 && (
        <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
          Nothing pinned yet — search above to start an investigation.
        </p>
      )}

      {groups.map(({ kind, items }) => (
        <div key={kind}>
          <CDLabel>{GROUP_LABELS[kind]}</CDLabel>
          <ul className="mt-2 space-y-1">
            {items.map((entity, index) => (
              <li
                key={entityKey(entity)}
                draggable
                onDragStart={() => setDragging({ kind, index })}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  if (dragging && dragging.kind === kind) onReorder(kind, dragging.index, index)
                  setDragging(null)
                }}
                onDragEnd={() => setDragging(null)}
              >
                <RailRow
                  entity={entity}
                  active={entityKey(entity) === focusedKey}
                  onFocus={() => onFocus(entity)}
                  onRemove={() => onUnpin(entity)}
                  draggableHandle
                />
              </li>
            ))}
          </ul>
        </div>
      ))}

      {unpinnedRecent.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5">
            <HistoryIcon className="size-3" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
            <CDLabel>Recently opened</CDLabel>
          </div>
          <ul className="mt-2 space-y-1">
            {unpinnedRecent.slice(0, 8).map((entity) => (
              <li key={entityKey(entity)}>
                <RailRow entity={entity} active={entityKey(entity) === focusedKey} onFocus={() => onFocus(entity)} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function RailRow({
  entity,
  active,
  onFocus,
  onRemove,
  draggableHandle,
}: {
  entity: WorkspaceEntity
  active: boolean
  onFocus: () => void
  onRemove?: () => void
  draggableHandle?: boolean
}) {
  return (
    <div
      className="group flex items-center gap-1.5 rounded-[var(--cd-radius-md)] px-1.5 py-1.5 transition-colors duration-[var(--cd-motion-snap)]"
      style={{ backgroundColor: active ? 'var(--cd-accent-muted)' : 'transparent' }}
    >
      {draggableHandle && (
        <GripVertical
          className="size-3 shrink-0 cursor-grab opacity-0 transition-opacity group-hover:opacity-100"
          style={{ color: 'var(--cd-text-muted)' }}
          aria-hidden="true"
        />
      )}
      <button type="button" onClick={onFocus} className="flex min-w-0 flex-1 items-center gap-2 text-left">
        {entity.logoUrl ? (
          <img src={entity.logoUrl} alt="" className="size-5 shrink-0 object-contain" loading="lazy" />
        ) : (
          <span
            className="flex size-5 shrink-0 items-center justify-center rounded-full font-[var(--cd-font-display)] text-[9px] font-semibold"
            style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
          >
            {entity.label.charAt(0).toUpperCase()}
          </span>
        )}
        <span
          className="truncate font-[var(--cd-font-body)] text-[12.5px]"
          style={{ color: active ? 'var(--cd-accent)' : 'var(--cd-text-primary)', fontWeight: active ? 600 : 400 }}
        >
          {entity.label}
        </span>
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${entity.label}`}
          className="shrink-0 rounded-full p-0.5 opacity-0 transition-opacity group-hover:opacity-100"
          style={{ color: 'var(--cd-text-muted)' }}
        >
          <X className="size-3" aria-hidden="true" />
        </button>
      )}
    </div>
  )
}
