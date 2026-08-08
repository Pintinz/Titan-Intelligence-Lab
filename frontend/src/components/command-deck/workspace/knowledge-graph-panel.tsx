import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronLeft, ZoomIn, ZoomOut, Waypoints, ExternalLink } from 'lucide-react'
import { graphApi } from '@/lib/api/graph'
import { ErrorState } from '@/components/ui/error-state'
import { CDLabel } from '../primitives/panel'
import { CD_DOMAIN_COLOR_VAR } from '../primitives/domain'
import { kgNodeTypeFor, type EntityKind, type WorkspaceEntity } from '@/lib/hooks/use-investigation-workspace'
import type { KgNodeDto } from '@/lib/api/types'

/** Real KG node types this workspace can re-focus on — the inverse of `kgNodeTypeFor`. Every
 * other node type (news_article, model, prediction, …) still renders and can be expanded, but
 * has no "open in workspace" affordance since it isn't one of the workspace's four entity kinds. */
const FOCUSABLE_NODE_TYPES: Record<string, EntityKind> = { team: 'team', player: 'player', competition: 'competition', match: 'fixture' }

/** Display order mirrors the brief's own chain (Match → Teams → Players → Competition → Managers
 * → Related Fixtures → News → Predictions). Manager/coach/referee never appear in practice — those
 * `NodeType` members are ontology-only with no population writer — but the order is kept so that
 * if a writer ever ships, it slots in without a layout change. */
const GROUP_ORDER = ['team', 'player', 'competition', 'manager', 'match', 'news_article', 'news_event', 'prediction']

/** `entity_ref` is an internal UUID for most node types (e.g. `match` nodes are populated with no
 * attributes at all — confirmed in `population_service.py`'s `populate_fixture`, which upserts
 * the node with no `attributes` dict). Never fall back to it as a visible label — that would leak
 * a raw internal identifier onto the graph. Falling back to a humanized node-type name instead
 * (e.g. "Match") is honest: it claims nothing the node doesn't actually carry. */
function humanizeNodeType(nodeType: string): string {
  return nodeType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function nodeLabel(node: KgNodeDto): string {
  const attrName = node.attributes && typeof node.attributes.name === 'string' ? (node.attributes.name as string) : null
  return attrName ?? node.aliases[0] ?? humanizeNodeType(node.node_type)
}

interface PositionedNode {
  node: KgNodeDto
  x: number
  y: number
  isSubject: boolean
}

const SIZE = 420
const CENTER = SIZE / 2

function layout(subject: KgNodeDto, relatedByType: Record<string, KgNodeDto[]>, hiddenTypes: Set<string>): PositionedNode[] {
  const groups = GROUP_ORDER.map((type) => ({ type, nodes: relatedByType[type] ?? [] })).filter(
    (g) => g.nodes.length > 0 && !hiddenTypes.has(g.type),
  )
  const positioned: PositionedNode[] = [{ node: subject, x: CENTER, y: CENTER, isSubject: true }]
  const ringGap = 300 / Math.max(1, groups.length + 1)

  groups.forEach((group, groupIndex) => {
    const radius = ringGap * (groupIndex + 1) * 0.62 + 70
    const count = group.nodes.length
    group.nodes.forEach((node, i) => {
      const angleSpan = Math.min(300, 40 + count * 26) // degrees allotted to this ring
      const startAngle = -angleSpan / 2 + (groupIndex % 2 === 0 ? 0 : 60)
      const angleDeg = count === 1 ? startAngle + angleSpan / 2 : startAngle + (angleSpan / (count - 1)) * i
      const angleRad = (angleDeg * Math.PI) / 180 - Math.PI / 2
      positioned.push({ node, x: CENTER + radius * Math.cos(angleRad), y: CENTER + radius * Math.sin(angleRad), isSubject: false })
    })
  })

  return positioned
}

/**
 * KnowledgeGraphPanel — real, hand-built SVG node-link view (no graph-viz library installed, and
 * this doesn't warrant adding one). Backed entirely by `graphApi.context()`, which returns the
 * subject node, its real 1-hop neighborhood edges, and nodes grouped by real `NodeType` — nothing
 * here is a mock layout. `variant="panel"` is the persistent desktop/tablet chrome (with its own
 * collapse toggle covering the tablet story); `variant="drawer"` strips that chrome for a mobile
 * bottom sheet the caller mounts conditionally.
 */
export function KnowledgeGraphPanel({
  entity,
  onFocusEntity,
  variant = 'panel',
  collapsed,
  onToggleCollapsed,
}: {
  entity: WorkspaceEntity | null
  onFocusEntity: (entity: WorkspaceEntity) => void
  variant?: 'panel' | 'drawer'
  collapsed?: boolean
  onToggleCollapsed?: () => void
}) {
  const [centerOverride, setCenterOverride] = useState<{ nodeId: string; nodeType: string; entityRef: string } | null>(null)
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())
  const [zoom, setZoom] = useState(1)

  const nodeType = centerOverride?.nodeType ?? (entity ? kgNodeTypeFor(entity.kind) : null)
  const entityRef = centerOverride?.entityRef ?? entity?.id ?? null

  const nodeQuery = useQuery({
    queryKey: ['graph', 'entity', nodeType, entityRef],
    queryFn: () => graphApi.getEntity(nodeType!, entityRef!),
    enabled: !!nodeType && !!entityRef,
    retry: false,
  })

  const contextQuery = useQuery({
    queryKey: ['graph', 'context', nodeQuery.data?.id],
    queryFn: () => graphApi.context(nodeQuery.data!.id, { depth: 1, max_nodes: 60 }),
    enabled: !!nodeQuery.data,
  })

  const positioned = useMemo(() => {
    if (!contextQuery.data) return []
    return layout(contextQuery.data.subject, contextQuery.data.related_by_type, hiddenTypes)
  }, [contextQuery.data, hiddenTypes])

  const availableTypes = contextQuery.data ? Object.keys(contextQuery.data.related_by_type).filter((t) => (contextQuery.data!.related_by_type[t]?.length ?? 0) > 0) : []

  function toggleType(type: string) {
    setHiddenTypes((prev) => {
      const next = new Set(prev)
      if (next.has(type)) next.delete(type)
      else next.add(type)
      return next
    })
  }

  function handleNodeClick(node: KgNodeDto) {
    setCenterOverride({ nodeId: node.id, nodeType: node.node_type, entityRef: node.entity_ref })
  }

  function handleOpen(node: KgNodeDto) {
    const kind = FOCUSABLE_NODE_TYPES[node.node_type]
    if (!kind) return
    onFocusEntity({ kind, id: node.entity_ref, label: nodeLabel(node) })
  }

  const chromeClass =
    variant === 'panel'
      ? `flex flex-col overflow-hidden rounded-[var(--cd-radius-lg)] border transition-[width] duration-[var(--cd-motion-base)] ${collapsed ? 'w-12' : 'w-full'}`
      : 'flex h-full flex-col'

  return (
    <div className={chromeClass} style={variant === 'panel' ? { borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)' } : undefined}>
      <div className="flex items-center justify-between gap-2 border-b p-3" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        {(!collapsed || variant === 'drawer') && (
          <div className="flex items-center gap-1.5">
            <Waypoints className="size-3.5" style={{ color: CD_DOMAIN_COLOR_VAR['knowledge-graph'] }} aria-hidden="true" />
            <CDLabel>Knowledge Graph</CDLabel>
          </div>
        )}
        {variant === 'panel' && onToggleCollapsed && (
          <button type="button" onClick={onToggleCollapsed} aria-label={collapsed ? 'Expand Knowledge Graph panel' : 'Collapse Knowledge Graph panel'} className="rounded-[var(--cd-radius-sm)] p-1" style={{ color: 'var(--cd-text-muted)' }}>
            {collapsed ? <ChevronLeft className="size-4" aria-hidden="true" /> : <ChevronRight className="size-4" aria-hidden="true" />}
          </button>
        )}
      </div>

      {(!collapsed || variant === 'drawer') && (
        <div className="flex-1 overflow-y-auto p-3">
          {!entity && (
            <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
              Focus a match, team, competition, or player to explore its Knowledge Graph relationships.
            </p>
          )}

          {entity && (nodeQuery.isPending || contextQuery.isPending) && (
            <div className="space-y-2">
              <p className="font-[var(--cd-font-telemetry)] text-[10.5px] uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
                Loading Knowledge Graph…
              </p>
              <div className="h-64 animate-pulse rounded-[var(--cd-radius-md)] motion-reduce:animate-none" style={{ backgroundColor: 'var(--cd-surface-2)' }} />
            </div>
          )}

          {entity && nodeQuery.isError && (
            <p className="font-[var(--cd-font-body)] text-[12px]" style={{ color: 'var(--cd-text-muted)' }}>
              Not yet linked in the Knowledge Graph.
            </p>
          )}

          {entity && contextQuery.isError && <ErrorState error={contextQuery.error} onRetry={() => void contextQuery.refetch()} />}

          {contextQuery.data && (
            <>
              {availableTypes.length > 0 && (
                <div className="mb-3 flex flex-wrap gap-1.5">
                  {availableTypes.map((type) => (
                    <button
                      key={type}
                      type="button"
                      onClick={() => toggleType(type)}
                      className="rounded-full border px-2 py-0.5 font-[var(--cd-font-telemetry)] text-[9.5px] uppercase tracking-[0.05em] transition-colors duration-[var(--cd-motion-snap)]"
                      style={{
                        borderColor: hiddenTypes.has(type) ? 'var(--cd-border-default)' : CD_DOMAIN_COLOR_VAR['knowledge-graph'],
                        color: hiddenTypes.has(type) ? 'var(--cd-text-muted)' : CD_DOMAIN_COLOR_VAR['knowledge-graph'],
                        opacity: hiddenTypes.has(type) ? 0.6 : 1,
                      }}
                    >
                      {type.replace('_', ' ')} ({contextQuery.data!.related_by_type[type].length})
                    </button>
                  ))}
                </div>
              )}

              <div className="relative overflow-hidden rounded-[var(--cd-radius-md)]" style={{ backgroundColor: 'var(--cd-surface-2)' }}>
                <svg viewBox={`0 0 ${SIZE} ${SIZE}`} width="100%" style={{ transform: `scale(${zoom})`, transformOrigin: 'center' }}>
                  {positioned.map(({ node }) =>
                    contextQuery.data!.neighborhood.edges
                      .filter((e) => e.from_node_id === node.id || e.to_node_id === node.id)
                      .map((edge) => {
                        const other = positioned.find((p) => p.node.id === (edge.from_node_id === node.id ? edge.to_node_id : edge.from_node_id))
                        const self = positioned.find((p) => p.node.id === node.id)
                        if (!other || !self) return null
                        return (
                          <line
                            key={`${edge.from_node_id}-${edge.to_node_id}-${edge.edge_type}`}
                            x1={self.x}
                            y1={self.y}
                            x2={other.x}
                            y2={other.y}
                            stroke="var(--cd-border-default)"
                            strokeWidth={1}
                          />
                        )
                      }),
                  )}

                  {positioned.map(({ node, x, y, isSubject }) => {
                    const focusable = !!FOCUSABLE_NODE_TYPES[node.node_type]
                    return (
                      <g key={node.id} transform={`translate(${x},${y})`} style={{ cursor: 'pointer' }} onClick={() => handleNodeClick(node)}>
                        <circle
                          r={isSubject ? 16 : 10}
                          fill={isSubject ? CD_DOMAIN_COLOR_VAR['knowledge-graph'] : 'var(--cd-surface-3)'}
                          stroke={isSubject ? 'transparent' : 'var(--cd-border-strong)'}
                          strokeWidth={1}
                        />
                        <text y={isSubject ? 28 : 22} textAnchor="middle" fontSize={9} fill="var(--cd-text-secondary)" style={{ fontFamily: 'var(--cd-font-body)' }}>
                          {nodeLabel(node).slice(0, 14)}
                        </text>
                        {focusable && !isSubject && (
                          <circle r={3} cx={9} cy={-9} fill={CD_DOMAIN_COLOR_VAR['knowledge-graph']} onClick={(e) => { e.stopPropagation(); handleOpen(node) }} />
                        )}
                      </g>
                    )
                  })}
                </svg>

                <div className="absolute bottom-2 right-2 flex gap-1">
                  <button type="button" onClick={() => setZoom((z) => Math.min(2, z + 0.2))} aria-label="Zoom in" className="rounded-[var(--cd-radius-sm)] border p-1" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-muted)' }}>
                    <ZoomIn className="size-3" aria-hidden="true" />
                  </button>
                  <button type="button" onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))} aria-label="Zoom out" className="rounded-[var(--cd-radius-sm)] border p-1" style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'var(--cd-surface-1)', color: 'var(--cd-text-muted)' }}>
                    <ZoomOut className="size-3" aria-hidden="true" />
                  </button>
                </div>
              </div>

              <p className="mt-2 font-[var(--cd-font-body)] text-[10.5px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
                Click a node to expand its own connections. The small dot opens a team, player, competition, or match directly in the workspace.
              </p>

              {FOCUSABLE_NODE_TYPES[contextQuery.data.subject.node_type] && centerOverride && (
                <button
                  type="button"
                  onClick={() => handleOpen(contextQuery.data!.subject)}
                  className="mt-2 inline-flex items-center gap-1 font-[var(--cd-font-body)] text-[11px] font-medium"
                  style={{ color: CD_DOMAIN_COLOR_VAR['knowledge-graph'] }}
                >
                  <ExternalLink className="size-3" aria-hidden="true" /> Open {nodeLabel(contextQuery.data.subject)} in workspace
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
