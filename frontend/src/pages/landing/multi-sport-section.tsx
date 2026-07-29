import { useState } from 'react'
import { FEATURED_MATCHES, SPORTS, type SportCode } from '@/pages/landing/sample-data'
import { ConfidenceTelemetry, IllustrativeTag, Section, SectionHeading } from '@/pages/landing/telemetry'

/**
 * Same Intelligence Center architecture across every sport (Live/Match/Team/Player/Competition/
 * Prediction Laboratory/News/Community) — only the market vocabulary differs. Table Tennis is
 * shown here, not Tennis: the backend's Phase One sports are Football, Basketball, Baseball, and
 * Table Tennis (docs/titaniq.md §3) — Tennis has no provider or plugin yet, so its market list
 * from the brief is adapted 1:1 onto Table Tennis's actual set-based structure below.
 */
const MARKETS: Record<SportCode, string[]> = {
  football: ['Match Winner', 'Double Chance', 'BTTS', 'Over/Under', 'Correct Score', 'Corners', 'Cards', 'First Half', 'Second Half'],
  basketball: ['Winner', 'Spread', 'Total Points', 'Team Points', 'First Half Total', 'Second Half Total', 'Quarter Markets'],
  baseball: ['Winner', 'Run Line', 'Total Runs', 'Team Runs', 'First 5 Innings', 'Innings Markets'],
  table_tennis: ['Match Winner', 'Set Winner', 'Correct Set Score', 'Total Points', 'Handicap Points', 'First Set Markets'],
}

export function MultiSportSection() {
  const [active, setActive] = useState<SportCode>('football')
  const match = FEATURED_MATCHES.find((m) => m.seed.sport === active) ?? FEATURED_MATCHES[0]

  return (
    <Section id="multi-sport" className="pt-0">
      <SectionHeading
        eyebrow="Multi-Sport Intelligence"
        title="One architecture. Every sport."
        description="Live, Match, Team, Player, Competition, Prediction Laboratory, News, and Community Intelligence — identical structure across sports. Only the markets change."
        action={<IllustrativeTag />}
      />

      <div className="mt-8 flex flex-wrap gap-2" role="tablist" aria-label="Choose a sport">
        {SPORTS.map((sport) => (
          <button
            key={sport.code}
            type="button"
            role="tab"
            aria-selected={active === sport.code}
            onClick={() => setActive(sport.code)}
            className="tl-eyebrow rounded-md px-4 py-2 transition-colors"
            style={{
              background: active === sport.code ? 'var(--tl-signal)' : 'var(--tl-carbon-raised)',
              color: active === sport.code ? 'var(--tl-void)' : 'var(--tl-ink-dim)',
              border: '1px solid var(--tl-steel-line)',
              fontSize: '0.7rem',
            }}
          >
            {sport.label}
          </button>
        ))}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="rounded-lg p-6" style={{ background: 'var(--tl-carbon-raised)', border: '1px solid var(--tl-steel-line)' }}>
          <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.65rem' }}>
            Top pick · {match.fixture.competition_name}
          </span>
          <h3 className="tl-display mt-2 text-2xl" style={{ color: 'var(--tl-ink)' }}>
            {match.fixture.home_team.name} vs {match.fixture.away_team.name}
          </h3>
          <p className="mt-2 text-sm" style={{ color: 'var(--tl-ink-dim)' }}>
            {match.seed.narrative}
          </p>
          <div className="mt-4">
            <ConfidenceTelemetry composite={match.seed.composite} />
          </div>
        </div>

        <div className="rounded-lg p-6" style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}>
          <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-dim)', fontSize: '0.65rem' }}>
            Prediction Markets
          </span>
          <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
            {MARKETS[active].map((market) => (
              <li key={market} className="flex items-center gap-2 text-sm" style={{ color: 'var(--tl-ink)' }}>
                <span className="h-1 w-1 rounded-full" style={{ background: 'var(--tl-signal)' }} />
                {market}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Section>
  )
}
