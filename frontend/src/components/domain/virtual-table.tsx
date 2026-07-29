import { type ReactNode, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { cn } from '@/lib/cn'

export interface VirtualTableColumn<T> {
  key: string
  header: string
  width?: string
  render: (row: T) => ReactNode
  align?: 'left' | 'right' | 'center'
}

export interface VirtualTableProps<T> {
  rows: T[]
  columns: Array<VirtualTableColumn<T>>
  getRowId: (row: T) => string
  rowHeight?: number
  maxHeight?: number
  onRowClick?: (row: T) => void
  emptyMessage?: string
}

/**
 * Row-virtualized table (@tanstack/react-virtual) for large lists — predictions, audit logs,
 * sync runs — where rendering every row would be the actual bottleneck. Small lists pay a
 * negligible fixed cost for the same component, so there's no separate non-virtualized variant.
 */
export function VirtualTable<T>({
  rows,
  columns,
  getRowId,
  rowHeight = 44,
  maxHeight = 480,
  onRowClick,
  emptyMessage = 'No results',
}: VirtualTableProps<T>) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
  })

  return (
    <div className="overflow-hidden rounded-lg border border-border-default">
      <div className="grid border-b border-border-default bg-bg-secondary text-xs font-medium uppercase tracking-wide text-text-muted" style={gridTemplate(columns)}>
        {columns.map((col) => (
          <div key={col.key} className={cn('px-3 py-2', alignClass(col.align))}>
            {col.header}
          </div>
        ))}
      </div>

      {rows.length === 0 ? (
        <div className="p-8 text-center text-sm text-text-muted">{emptyMessage}</div>
      ) : (
        <div ref={scrollRef} className="overflow-y-auto" style={{ maxHeight }}>
          <div style={{ height: virtualizer.getTotalSize(), position: 'relative' }}>
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const row = rows[virtualRow.index]
              return (
                <div
                  key={getRowId(row)}
                  className={cn(
                    'absolute left-0 top-0 grid w-full items-center border-b border-border-subtle text-sm text-text-primary',
                    onRowClick && 'cursor-pointer hover:bg-bg-secondary',
                  )}
                  style={{ height: virtualRow.size, transform: `translateY(${virtualRow.start}px)`, ...gridTemplate(columns) }}
                  onClick={() => onRowClick?.(row)}
                >
                  {columns.map((col) => (
                    <div key={col.key} className={cn('truncate px-3', alignClass(col.align))}>
                      {col.render(row)}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function gridTemplate<T>(columns: Array<VirtualTableColumn<T>>) {
  return { gridTemplateColumns: columns.map((c) => c.width ?? '1fr').join(' ') }
}

function alignClass(align?: 'left' | 'right' | 'center') {
  if (align === 'right') return 'text-right'
  if (align === 'center') return 'text-center'
  return 'text-left'
}
