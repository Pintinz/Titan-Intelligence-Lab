import { ListChecks, CircleCheck, TriangleAlert, ShieldAlert } from 'lucide-react'
import { humanizeFactorKey, type TeamRef } from '@/components/infinity/evidence-explorer'
import { predictionValueLabel } from '@/lib/predictions/value-label'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import type { RankedIntelligenceItem } from '@/lib/hooks/use-priority-intelligence'
import { CDButton } from '../primitives/button'
import { CDConfidenceGauge } from '../primitives/gauge'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'

function sportSlugFor(code: string): string {
  return SPORT_SLUGS.find((s) => s.code === code)?.slug ?? code
}

function confidenceTierLabel(pct: number): string {
  if (pct >= 95) return 'Elite'
  if (pct >= 85) return 'High'
  if (pct >= 75) return 'Strong'
  return 'Moderate'
}

/**
 * Priority Intelligence — ranks 1-3 of the same pool Intelligence Now (rank 0) already drew from,
 * so a match never appears twice. Every "Key drivers" bullet is a real SHAP-backed top feature,
 * never generic copy.
 */
export function PriorityIntelligence({ items, isLoading }: { items: RankedIntelligenceItem[]; isLoading: boolean }) {
  return (
    <MissionSection
      id="priority-intelligence"
      title="Priority Intelligence"
      subtitle="Signals worth investigating now"
      icon={<ListChecks className="size-4" aria-hidden="true" />}
      domain="predictions"
    >
      {isLoading && <MissionSkeletonGrid count={3} />}
      {!isLoading && items.length === 0 && (
        <MissionEmptyState
          icon={ListChecks}
          title="No further signals yet."
          description="Priority Intelligence fills in as more predictions clear TitanIQ's confidence floor."
        />
      )}
      {!isLoading && items.length > 0 && (
        <MissionCardGrid>
          {items.map((item) => (
            <PriorityCard key={item.pick.id} item={item} />
          ))}
        </MissionCardGrid>
      )}
    </MissionSection>
  )
}

function PriorityCard({ item }: { item: RankedIntelligenceItem }) {
  const { pick, fixture } = item
  const homeTeam: TeamRef = { name: fixture.home_team.name, logoUrl: fixture.home_team.logo_url }
  const awayTeam: TeamRef = { name: fixture.away_team.name, logoUrl: fixture.away_team.logo_url }
  const confidencePct = Math.round(pick.confidence_composite * 100)
  const probabilityPct = Math.round(pick.probability * 100)
  const href = `/app/${sportSlugFor(pick.sport_code)}/matches/${fixture.id}`
  const injuryCount = item.homeInjuries.length + item.awayInjuries.length

  return (
    <div
      className="flex flex-col gap-3.5 rounded-[var(--cd-radius-2xl)] p-4 backdrop-blur-md transition-all duration-[var(--cd-motion-base)] hover:-translate-y-0.5 hover:shadow-[var(--cd-card-shadow-hover)]"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)', boxShadow: 'var(--cd-card-shadow)' }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate font-[var(--cd-font-telemetry)] text-[10px] font-medium uppercase tracking-[0.06em]" style={{ color: 'var(--cd-text-muted)' }}>
          {fixture.competition_name}
        </span>
        <CDConfidenceGauge value={pick.confidence_composite} size={40} />
      </div>

      <div>
        <p className="truncate font-[var(--cd-font-body)] text-[13.5px] font-semibold" style={{ color: 'var(--cd-text-primary)' }}>
          {homeTeam.name} <span style={{ color: 'var(--cd-text-muted)' }}>vs</span> {awayTeam.name}
        </p>
        <p className="mt-1.5 font-[var(--cd-font-display)] text-[10.5px] font-medium uppercase tracking-[0.04em]" style={{ color: 'var(--cd-text-muted)' }}>{pick.market_name}</p>
        <p className="mt-0.5 font-[var(--cd-font-display)] text-[16px] font-bold" style={{ color: 'var(--cd-text-primary)' }}>
          {predictionValueLabel(pick.value, homeTeam, awayTeam)}{' '}
          <span className="font-[var(--cd-font-tabular)] text-[13px] font-semibold tabular-nums" style={{ color: 'var(--cd-accent)' }}>{probabilityPct}%</span>
        </p>
        <p className="font-[var(--cd-font-telemetry)] text-[9.5px] uppercase tracking-[0.05em]" style={{ color: 'var(--cd-text-muted)' }}>{confidenceTierLabel(confidencePct)} confidence</p>
      </div>

      {(item.topPositiveFeatures.length > 0 || item.topNegativeFeatures.length > 0) && (
        <ul className="space-y-1">
          {item.topPositiveFeatures.slice(0, 2).map(([key]) => (
            <li key={key} className="flex items-start gap-1.5">
              <CircleCheck className="mt-0.5 size-3 shrink-0" style={{ color: 'var(--cd-positive)' }} aria-hidden="true" />
              <span className="font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>{humanizeFactorKey(key)}</span>
            </li>
          ))}
          {item.topNegativeFeatures.slice(0, 1).map(([key]) => (
            <li key={key} className="flex items-start gap-1.5">
              <TriangleAlert className="mt-0.5 size-3 shrink-0" style={{ color: 'var(--cd-negative)' }} aria-hidden="true" />
              <span className="font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>{humanizeFactorKey(key)}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center gap-1.5 border-t pt-2.5" style={{ borderColor: 'var(--cd-border-hairline)' }}>
        <ShieldAlert className="size-3 shrink-0" style={{ color: injuryCount > 0 ? 'var(--cd-negative)' : 'var(--cd-text-muted)' }} aria-hidden="true" />
        <span className="line-clamp-1 font-[var(--cd-font-body)] text-[11px]" style={{ color: 'var(--cd-text-muted)' }}>
          {injuryCount > 0 ? `${injuryCount} verified context ${injuryCount === 1 ? 'item' : 'items'}` : 'No verified lineup issue'}
        </span>
      </div>

      <CDButton variant="secondary" size="sm" href={href} className="justify-center">
        Investigate
      </CDButton>
    </div>
  )
}
