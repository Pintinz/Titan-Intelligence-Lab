import { ClipboardCheck } from 'lucide-react'
import { SPORT_SLUGS } from '@/lib/hooks/use-sport'
import { useRecentlyCompletedIntelligence } from '@/lib/hooks/use-recently-completed-intelligence'
import { ReviewedFixtureCard } from '../discovery/recently-completed-intelligence'
import { MissionSection, MissionCardGrid, MissionSkeletonGrid, MissionEmptyState } from './mission-section'

/** Cross-sport "Recently Completed Intelligence" for Mission Control — same shared hook and card
 * as the single-sport Match Discovery rail, just fanned out across every sport and capped at 6. */
export function RecentlyCompletedCrossSport() {
  const { reviewed, isLoading } = useRecentlyCompletedIntelligence(
    SPORT_SLUGS.map((s) => ({ code: s.code, slug: s.slug })),
    6,
  )

  const header = {
    subtitle: 'Predicted vs. actual, resolved and scored',
    icon: <ClipboardCheck className="size-4" aria-hidden="true" />,
    domain: 'learning' as const,
  }

  if (!isLoading && reviewed.length === 0) {
    return (
      <MissionSection id="recently-completed" title="Recently Completed Intelligence" {...header}>
        <MissionEmptyState
          icon={ClipboardCheck}
          title="No AI reviews resolved yet."
          description="Once a match finishes and TitanIQ resolves its predictions, the review appears here — predicted vs. actual, real evidence, no guessing."
        />
      </MissionSection>
    )
  }

  return (
    <MissionSection id="recently-completed" title="Recently Completed Intelligence" {...header}>
      {isLoading && <MissionSkeletonGrid />}
      {!isLoading && (
        <MissionCardGrid>
          {reviewed.map((row) => (
            <ReviewedFixtureCard key={row.fixture.id} row={row} />
          ))}
        </MissionCardGrid>
      )}
    </MissionSection>
  )
}
