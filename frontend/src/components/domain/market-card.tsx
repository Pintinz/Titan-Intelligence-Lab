import { cn } from '@/lib/cn'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { PredictionMarketDto } from '@/lib/api/types'

const statusVariant: Record<string, 'success' | 'accent' | 'neutral' | 'warning'> = {
  production: 'success',
  approved: 'accent',
  review: 'warning',
  draft: 'neutral',
  deprecated: 'neutral',
  archived: 'neutral',
  removed: 'neutral',
}

export function MarketCard({
  market,
  selected,
  onSelect,
}: {
  market: PredictionMarketDto
  selected?: boolean
  onSelect?: () => void
}) {
  return (
    <Card
      className={cn(
        'cursor-pointer p-4 transition-colors',
        selected ? 'border-accent-primary' : 'hover:border-border-strong',
      )}
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect?.()}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-display text-sm font-semibold text-text-primary">{market.name}</p>
        <Badge variant={statusVariant[market.status] ?? 'neutral'}>{market.status}</Badge>
      </div>
      <p className="mt-1 font-mono text-xs text-text-muted">{market.market_key}</p>
      <p className="mt-2 text-xs text-text-secondary">{market.description}</p>
      <p className="mt-2 text-[11px] text-text-muted">
        Confidence threshold {Math.round(market.confidence_threshold * 100)}%
      </p>
    </Card>
  )
}
