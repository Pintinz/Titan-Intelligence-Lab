function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length === 0 ? '—' : value.map(formatValue).join(', ')
  if (isPlainObject(value)) return Object.keys(value).length === 0 ? '—' : ''
  return String(value)
}

/**
 * Several backend endpoints (predictions monitoring/statistics summaries) return a plain
 * `Record<string, unknown>` rather than a typed DTO — no `_serialize_*` shape exists to bind to.
 * This renders whatever comes back honestly instead of guessing at field names. A nested object
 * value (e.g. `predictions_by_status: {"draft": 1}`) is broken out as its own mini list rather
 * than `JSON.stringify`-ed, so the user never sees raw `{"draft":1}` braces on screen.
 */
export function KeyValueGrid({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data)

  if (entries.length === 0) {
    return <p className="text-sm text-text-secondary">No data returned.</p>
  }

  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
      {entries.map(([key, value]) => (
        <div key={key} className="min-w-0">
          <dt className="text-xs text-text-muted">{formatKey(key)}</dt>
          {isPlainObject(value) && Object.keys(value).length > 0 ? (
            <dd className="mt-1 space-y-0.5">
              {Object.entries(value).map(([subKey, subValue]) => (
                <div key={subKey} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-text-muted">{formatKey(subKey)}</span>
                  <span className="break-words font-mono tabular-nums text-text-primary">{formatValue(subValue)}</span>
                </div>
              ))}
            </dd>
          ) : (
            <dd className="break-words font-mono text-sm tabular-nums text-text-primary">{formatValue(value)}</dd>
          )}
        </div>
      ))}
    </dl>
  )
}
