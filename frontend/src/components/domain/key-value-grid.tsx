function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/**
 * Several backend endpoints (predictions monitoring/statistics summaries) return a plain
 * `Record<string, unknown>` rather than a typed DTO — no `_serialize_*` shape exists to bind to.
 * This renders whatever comes back honestly instead of guessing at field names.
 */
export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return <p className="text-sm text-text-secondary">No data returned.</p>
  }

  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt className="text-xs text-text-muted">{formatKey(key)}</dt>
          <dd className="font-mono text-sm tabular-nums text-text-primary">{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  )
}
