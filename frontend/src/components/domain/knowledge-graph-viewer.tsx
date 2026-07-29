import { useMemo, useState, type WheelEvent } from 'react'
import type { KgEdgeDto, KgNodeDto } from '@/lib/api/types'
import { cn } from '@/lib/cn'

export interface KnowledgeGraphViewerProps {
  centerNode: KgNodeDto
  neighbors: KgNodeDto[]
  edges: KgEdgeDto[]
  onNodeClick?: (node: KgNodeDto) => void
  className?: string
  height?: number
}

/**
 * Deterministic radial layout (center node fixed, neighbors placed by angle) rather than a force
 * simulation — cheap, stable across re-renders (no jitter as data streams in), and sufficient for
 * the single-hop neighborhoods this component is actually asked to render (see
 * src/pages/graph/graph-explorer-page.tsx for the traversal that expands further hops by
 * re-centering on a clicked node, rather than growing one simulation arbitrarily).
 */
export function KnowledgeGraphViewer({ centerNode, neighbors, edges, onNodeClick, className, height = 420 }: KnowledgeGraphViewerProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)

  const layout = useMemo(() => {
    const radius = 160
    const positions = new Map<string, { x: number; y: number }>()
    positions.set(centerNode.id, { x: 0, y: 0 })
    neighbors.forEach((node, index) => {
      const angle = (index / Math.max(1, neighbors.length)) * 2 * Math.PI
      positions.set(node.id, { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius })
    })
    return positions
  }, [centerNode.id, neighbors])

  function handleWheel(event: WheelEvent<SVGSVGElement>) {
    event.preventDefault()
    setZoom((z) => Math.min(2.5, Math.max(0.5, z - event.deltaY * 0.001)))
  }

  const allNodes = [centerNode, ...neighbors]
  const selected = allNodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className={cn('relative overflow-hidden rounded-lg border border-border-default bg-bg-secondary', className)} style={{ height }}>
      <svg
        viewBox={`${-260 / zoom} ${-260 / zoom} ${520 / zoom} ${520 / zoom}`}
        className="h-full w-full cursor-grab"
        onWheel={handleWheel}
        role="img"
        aria-label={`Knowledge graph neighborhood of ${centerNode.entity_ref}`}
      >
        {edges.map((edge, index) => {
          const from = positionOrOrigin(layout, edge.from_node_id)
          const to = positionOrOrigin(layout, edge.to_node_id)
          return (
            <line
              key={`${edge.from_node_id}-${edge.to_node_id}-${index}`}
              x1={from.x}
              y1={from.y}
              x2={to.x}
              y2={to.y}
              stroke="var(--color-border-strong)"
              strokeWidth={1}
            />
          )
        })}

        {allNodes.map((node) => {
          const pos = layout.get(node.id) ?? { x: 0, y: 0 }
          const isCenter = node.id === centerNode.id
          const isSelected = node.id === selectedId
          return (
            <g
              key={node.id}
              transform={`translate(${pos.x}, ${pos.y})`}
              className="cursor-pointer"
              onClick={() => {
                setSelectedId(node.id)
                onNodeClick?.(node)
              }}
            >
              <circle
                r={isCenter ? 14 : 9}
                fill={isCenter ? 'var(--color-accent-primary)' : 'var(--color-bg-elevated)'}
                stroke={isSelected ? 'var(--color-accent-primary)' : 'var(--color-border-strong)'}
                strokeWidth={isSelected ? 2 : 1}
              />
              <text
                y={isCenter ? 26 : 20}
                textAnchor="middle"
                fontSize={10}
                fill="var(--color-text-secondary)"
                className="select-none"
              >
                {truncate(node.entity_ref, 14)}
              </text>
            </g>
          )
        })}
      </svg>

      {selected && (
        <div className="absolute bottom-3 left-3 rounded-md border border-border-default bg-bg-elevated p-3 text-xs shadow-[var(--shadow-elevation-2)]">
          <p className="font-medium text-text-primary">{selected.entity_ref}</p>
          <p className="text-text-muted">{selected.node_type}</p>
        </div>
      )}
    </div>
  )
}

function positionOrOrigin(layout: Map<string, { x: number; y: number }>, id: string) {
  return layout.get(id) ?? { x: 0, y: 0 }
}

function truncate(value: string, max: number) {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}
