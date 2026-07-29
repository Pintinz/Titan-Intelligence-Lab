function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function formatLabel(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Renders a flat-ish dict from an untyped backend aggregate endpoint as label/value rows —
 * used where the response shape is a real dict we don't want to over-fit a strict interface to
 * (see analytics-center-page.tsx), while still looking like part of the product, not a debug dump. */
export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) {
    return <p className="text-sm text-text-muted">No data available.</p>
  }
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center justify-between gap-2 border-b border-border-subtle py-1.5 last:border-0">
          <dt className="text-text-muted">{formatLabel(key)}</dt>
          <dd className="truncate font-mono text-text-primary">{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  )
}
