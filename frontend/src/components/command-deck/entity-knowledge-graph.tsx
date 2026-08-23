import { Waypoints } from 'lucide-react'
import { CDPanel, CDLabel } from './primitives/panel'
import { ApiError } from '@/lib/api/client'
import type { KgContextDto, KgNodeDto } from '@/lib/api/types'

function humanizePlural(nodeType: string, count: number): string {
  const label = nodeType.replace(/_/g, ' ')
  if (count === 1 || label.endsWith('s')) return label
  return `${label}s`
}

/**
 * EntityKnowledgeGraphPanel — extracted from `player-detail-page.tsx`'s original
 * `KnowledgeGraphSection` (identical rendering, generalized `entityLabel` prop) so Player and
 * Competition Intelligence share one real Knowledge Graph rendering instead of two copies drifting
 * apart. Every count is `graphApi.context()`'s real related-node grouping — no relationship is
 * invented, and a 404/empty context renders the same honest "no connected entities yet" either way.
 */
export function EntityKnowledgeGraphPanel({
  nodeQuery,
  contextQuery,
  entityLabel,
}: {
  nodeQuery: { isPending: boolean; isError: boolean; error: unknown; data: KgNodeDto | undefined }
  contextQuery: { isPending: boolean; data: KgContextDto | undefined }
  entityLabel: string
}) {
  const notFound = nodeQuery.isError && nodeQuery.error instanceof ApiError && nodeQuery.error.status === 404
  const otherError = nodeQuery.isError && !notFound

  return (
    <CDPanel>
      <div className="flex items-center gap-2">
        <Waypoints className="size-4" style={{ color: 'var(--cd-text-muted)' }} aria-hidden="true" />
        <CDLabel>Connected intelligence</CDLabel>
      </div>

      {nodeQuery.isPending && <div className="mt-4 h-10 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />}

      {notFound && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          No connected entities are currently available for {entityLabel}.
        </p>
      )}

      {otherError && (
        <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
          Connected intelligence could not be loaded.
        </p>
      )}

      {nodeQuery.data && (
        <>
          {contextQuery.isPending && <div className="mt-3 h-8 animate-pulse rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }} />}
          {contextQuery.data &&
            (() => {
              const related = Object.entries(contextQuery.data.related_by_type)
              const total = related.reduce((sum, [, nodes]) => sum + nodes.length, 0)
              if (total === 0) {
                return (
                  <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    No connected entities are currently available for {entityLabel}.
                  </p>
                )
              }
              return (
                <>
                  <p className="mt-3 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-secondary)' }}>
                    TitanIQ has connected {entityLabel} to {total} related {total === 1 ? 'entity' : 'entities'} it uses to build
                    understanding.
                  </p>
                  <ul className="mt-3 flex flex-wrap gap-2">
                    {related.map(([type, nodes]) => (
                      <li key={type}>
                        <span
                          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-[var(--cd-font-telemetry)] text-[10.5px] font-medium"
                          style={{ color: 'var(--cd-accent)', backgroundColor: 'var(--cd-accent-muted)' }}
                        >
                          {nodes.length} {humanizePlural(type, nodes.length)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </>
              )
            })()}
        </>
      )}
    </CDPanel>
  )
}
