import { cn } from '@/lib/cn'

export interface FeatureContribution {
  feature_key: string
  contribution: number
}

/**
 * Horizontal diverging bar list — positive contributions extend right in success tone, negative
 * extend right in danger tone (all bars start at the left edge; this is a ranked-magnitude view,
 * not a zero-centered diverging chart, since the two lists are already split by sign upstream).
 */
export function FeatureImportanceBars({
  positive,
  negative,
  className,
}: {
  positive: FeatureContribution[]
  negative: FeatureContribution[]
  className?: string
}) {
  const maxMagnitude = Math.max(
    1e-6,
    ...positive.map((f) => Math.abs(f.contribution)),
    ...negative.map((f) => Math.abs(f.contribution)),
  )

  return (
    <div className={cn('grid gap-6 sm:grid-cols-2', className)}>
      <FeatureList title="Top positive features" items={positive} tone="success" maxMagnitude={maxMagnitude} />
      <FeatureList title="Top negative features" items={negative} tone="danger" maxMagnitude={maxMagnitude} />
    </div>
  )
}

function FeatureList({
  title,
  items,
  tone,
  maxMagnitude,
}: {
  title: string
  items: FeatureContribution[]
  tone: 'success' | 'danger'
  maxMagnitude: number
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{title}</span>
      {items.length === 0 && <span className="text-sm text-text-muted">None</span>}
      {items.map((item) => (
        <div key={item.feature_key} className="flex items-center gap-2">
          <span className="w-32 shrink-0 truncate font-mono text-xs text-text-secondary" title={item.feature_key}>
            {item.feature_key}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-bg-secondary">
            <div
              className={cn('h-full rounded-full', tone === 'success' ? 'bg-success' : 'bg-danger')}
              style={{ width: `${Math.round((Math.abs(item.contribution) / maxMagnitude) * 100)}%` }}
            />
          </div>
          <span className="w-14 shrink-0 text-right font-mono text-xs text-text-muted">
            {item.contribution.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  )
}
