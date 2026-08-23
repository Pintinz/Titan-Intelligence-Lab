import { Target } from 'lucide-react'
import { CDPanel, CDLabel } from './primitives/panel'
import { MissionEmptyState } from './mission-control/mission-section'
import { fixtureScores } from '@/lib/sports-status'
import type { FixtureSummaryDto } from '@/lib/api/types'

interface CompetitionStats {
  played: number
  goals: number
  goalsPerMatch: number
  homeWins: number
  draws: number
  awayWins: number
}

/** Every number here is a pure derivation of the competition's own already-fetched completed
 * fixtures (real final scores) — no separate statistics endpoint exists for a whole competition,
 * and none is needed: this is the exact same "count real completed fixtures" technique
 * `team-detail-page.tsx`'s own season analytics already uses, just aggregated across every team in
 * the competition instead of one. Cards, shots, possession, and discipline stay out entirely —
 * those live only on per-fixture `TeamStatistics` rows, and aggregating them competition-wide would
 * need a request per fixture with no bound the UI could justify. */
function computeCompetitionStats(completedFixtures: FixtureSummaryDto[]): CompetitionStats {
  let goals = 0
  let homeWins = 0
  let draws = 0
  let awayWins = 0
  let played = 0
  for (const fixture of completedFixtures) {
    const { homeScore, awayScore } = fixtureScores(fixture.final_state)
    if (homeScore === undefined || awayScore === undefined) continue
    played += 1
    goals += homeScore + awayScore
    if (homeScore > awayScore) homeWins += 1
    else if (homeScore < awayScore) awayWins += 1
    else draws += 1
  }
  return { played, goals, goalsPerMatch: played > 0 ? goals / played : 0, homeWins, draws, awayWins }
}

export function CompetitionStatisticsSection({ completedFixtures, seasonLabel }: { completedFixtures: FixtureSummaryDto[]; seasonLabel?: string }) {
  const stats = computeCompetitionStats(completedFixtures)

  if (stats.played === 0) {
    return (
      <MissionEmptyState
        icon={Target}
        title="Statistics unavailable"
        description="TitanIQ hasn't logged any completed fixtures with recorded scores for this competition yet."
      />
    )
  }

  const pct = (n: number) => Math.round((n / stats.played) * 100)

  return (
    <div className="space-y-4">
      <p className="font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
        {seasonLabel ? `${seasonLabel} · ` : ''}Based on {stats.played} completed {stats.played === 1 ? 'fixture' : 'fixtures'}
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <CDPanel padding="tight">
          <CDLabel>Total goals</CDLabel>
          <p className="mt-2 font-[var(--cd-font-tabular)] text-[26px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {stats.goals}
          </p>
        </CDPanel>
        <CDPanel padding="tight">
          <CDLabel>Goals / match</CDLabel>
          <p className="mt-2 font-[var(--cd-font-tabular)] text-[26px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {stats.goalsPerMatch.toFixed(2)}
          </p>
        </CDPanel>
        <CDPanel padding="tight">
          <CDLabel>Home wins</CDLabel>
          <p className="mt-2 font-[var(--cd-font-tabular)] text-[26px] font-semibold tabular-nums" style={{ color: 'var(--cd-positive)' }}>
            {pct(stats.homeWins)}%
          </p>
          <p className="mt-0.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
            {stats.homeWins} of {stats.played}
          </p>
        </CDPanel>
        <CDPanel padding="tight">
          <CDLabel>Away wins</CDLabel>
          <p className="mt-2 font-[var(--cd-font-tabular)] text-[26px] font-semibold tabular-nums" style={{ color: 'var(--cd-text-primary)' }}>
            {pct(stats.awayWins)}%
          </p>
          <p className="mt-0.5 font-[var(--cd-font-tabular)] text-[11px] tabular-nums" style={{ color: 'var(--cd-text-muted)' }}>
            {stats.awayWins} of {stats.played}
          </p>
        </CDPanel>
      </div>

      <CDPanel padding="tight">
        <CDLabel>Match outcomes</CDLabel>
        <div className="mt-3 flex h-2 overflow-hidden rounded-full" style={{ backgroundColor: 'var(--cd-surface-3)' }}>
          <div style={{ width: `${pct(stats.homeWins)}%`, backgroundColor: 'var(--cd-positive)' }} title={`Home wins ${pct(stats.homeWins)}%`} />
          <div style={{ width: `${pct(stats.draws)}%`, backgroundColor: 'var(--cd-text-muted)' }} title={`Draws ${pct(stats.draws)}%`} />
          <div style={{ width: `${pct(stats.awayWins)}%`, backgroundColor: 'var(--cd-accent)' }} title={`Away wins ${pct(stats.awayWins)}%`} />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-[var(--cd-font-body)] text-[11.5px]" style={{ color: 'var(--cd-text-secondary)' }}>
          <span>Home {pct(stats.homeWins)}%</span>
          <span>Draw {pct(stats.draws)}%</span>
          <span>Away {pct(stats.awayWins)}%</span>
        </div>
      </CDPanel>

      <p className="font-[var(--cd-font-body)] text-[10.5px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
        Statistics are calculated only from fixtures with a real recorded final score under TitanIQ's coverage — if the season isn't
        fully complete, these figures reflect the completed portion only, not a projected full-season total.
      </p>
    </div>
  )
}
