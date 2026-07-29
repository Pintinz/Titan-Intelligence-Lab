import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card } from '@/components/ui/card'
import { Section, SectionHeading } from './section-primitives'

const SPORTS = [
  {
    label: 'Football',
    markets: ['Match Winner', 'Both Teams to Score', 'Over/Under Goals', 'Correct Score', 'First Half Winner'],
  },
  {
    label: 'Basketball',
    markets: ['Moneyline', 'Point Spread', 'Total Points', 'Team Total Points', 'Race to 20 Points'],
  },
  {
    label: 'Baseball',
    markets: ['Moneyline', 'Run Line', 'Total Runs', 'Team Total Runs', 'First 5 Innings Winner'],
  },
  {
    label: 'Table Tennis',
    markets: ['Match Winner', 'Match Handicap', 'Total Points', 'Correct Score', 'Set Winner'],
  },
]

export function MultiSportSection() {
  return (
    <Section className="border-b border-border-subtle">
      <SectionHeading
        eyebrow="Multi-Sport Intelligence"
        title="One architecture, four sports"
        description="Every Sport Intelligence Center follows the same structure — Live, Match, Team, Player, Competition, and a Prediction Laboratory. Only the market list changes."
      />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SPORTS.map((sport) => (
          <Card key={sport.label} className="flex h-full flex-col p-5">
            <p className="font-display text-base font-semibold text-text-primary">{sport.label}</p>
            <ul className="mt-3 flex-1 space-y-1.5">
              {sport.markets.map((market) => (
                <li key={market} className="text-xs text-text-secondary">
                  {market}
                </li>
              ))}
            </ul>
            <Link
              to="/signup"
              className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-accent-primary hover:text-accent-primary-hover"
            >
              Open {sport.label} Intelligence <ArrowRight className="size-3" />
            </Link>
          </Card>
        ))}
      </div>
    </Section>
  )
}
