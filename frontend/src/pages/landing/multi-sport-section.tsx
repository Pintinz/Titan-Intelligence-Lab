import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { LiveDot } from '@/components/ui/live-dot'
import { Card } from '@/components/ui/card'
import { Section, SectionHeading } from './section-primitives'
import type { PublicSportSummaryDto } from '@/lib/api/types'

// Configured market catalogs per sport — real product configuration (modules/*/market_seeding.py),
// not live counts; the live coverage numbers below each list come from platform-summary.
const MARKETS_BY_SPORT: Record<string, string[]> = {
  football: ['Match Winner', 'Both Teams to Score', 'Over/Under Goals', 'Correct Score', 'First Half Winner'],
  basketball: ['Moneyline', 'Point Spread', 'Total Points', 'Team Total Points', 'Race to 20 Points'],
  baseball: ['Moneyline', 'Run Line', 'Total Runs', 'Team Total Runs', 'First 5 Innings Winner'],
  table_tennis: ['Match Winner', 'Match Handicap', 'Total Points', 'Correct Score', 'Set Winner'],
}

export function MultiSportSection({ loading, sports }: { loading: boolean; sports: PublicSportSummaryDto[] }) {
  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="Multi-Sport Intelligence"
        title="One architecture, four sports"
        description="Every Sport Intelligence Center follows the same structure — Live, Match, Team, Player, Competition, and a Prediction Laboratory. Only the market list changes."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-64 animate-pulse rounded-lg bg-bg-secondary" />)
          : sports.map((sport) => (
              <Card key={sport.code} className="flex h-full flex-col p-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-display text-base font-semibold text-text-primary">{sport.display_name}</p>
                  {sport.live_fixtures > 0 && (
                    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-live">
                      <LiveDot /> {sport.live_fixtures}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-text-muted">
                  {sport.competitions} competition{sport.competitions === 1 ? '' : 's'} tracked · {sport.today_fixtures} today
                </p>
                <ul className="mt-3 flex-1 space-y-1.5">
                  {(MARKETS_BY_SPORT[sport.code] ?? []).map((market) => (
                    <li key={market} className="text-xs text-text-secondary">
                      {market}
                    </li>
                  ))}
                </ul>
                <Link
                  to="/signup"
                  className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent-primary hover:text-accent-primary-hover"
                >
                  Open {sport.display_name} Intelligence <ArrowRight className="size-3" />
                </Link>
              </Card>
            ))}
      </div>
    </Section>
  )
}
