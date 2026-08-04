import { InfinityPanel, InfinityLabel } from '../primitives/panel'
import { InfinityBadge } from '../primitives/badge'

export interface NewsCardProps {
  headline: string
  source: string
  publishedAgo: string
  sentiment: 'positive' | 'neutral' | 'negative'
  confidenceImpact: number
}

const SENTIMENT_TONE: Record<NewsCardProps['sentiment'], string> = {
  positive: 'var(--infinity-success)',
  neutral: 'var(--infinity-text-muted)',
  negative: 'var(--infinity-danger)',
}

/** Never a headline-plus-thumbnail feed item — every article explains its prediction
 * impact directly on the card, per the brief's "transform journalism into intelligence." */
export function InfinityNewsCard({ headline, source, publishedAgo, sentiment, confidenceImpact }: NewsCardProps) {
  return (
    <InfinityPanel tone="var(--infinity-domain-news)">
      <div className="flex items-center justify-between">
        <InfinityLabel tone="var(--infinity-domain-news)">{source}</InfinityLabel>
        <span className="font-infinity-mono text-[10px] text-infinity-text-muted">{publishedAgo}</span>
      </div>
      <p className="mt-1.5 font-infinity-display text-[14px] font-semibold leading-snug text-infinity-text-primary">{headline}</p>
      <div className="mt-3 flex items-center justify-between border-t border-infinity-border-hairline pt-2.5">
        <InfinityBadge tone={SENTIMENT_TONE[sentiment]}>{sentiment}</InfinityBadge>
        <span className="font-infinity-mono text-[11px] text-infinity-text-secondary">
          Confidence impact {confidenceImpact >= 0 ? '+' : ''}
          {(confidenceImpact * 100).toFixed(1)}%
        </span>
      </div>
    </InfinityPanel>
  )
}
