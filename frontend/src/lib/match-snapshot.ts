import type { FixtureTeamStatisticsDto } from '@/lib/api/types'

export type MatchStats = FixtureTeamStatisticsDto['stats']

export type MatchResult = 'win' | 'draw' | 'loss'

export interface SnapshotStatChip {
  key: 'goals' | 'btts' | 'corners' | 'shots_on_target' | 'clean_sheet' | 'possession' | 'cards'
  label: string
  value: string
}

export interface MatchSnapshot {
  result: MatchResult
  stats: SnapshotStatChip[]
  summary: string
}

/**
 * AI Match Snapshot — a deterministic, rule-based reading of one past match, never an LLM call
 * (Milestone: Recent Form redesign brief). Every chip and every clause in `summary` is grounded
 * in a real value that was actually passed in; a stat this match's sync never recorded (corners,
 * shots on target, possession, cards — coverage is honestly sparse today) is simply omitted from
 * both the chip list and the summary, never padded with a guess. Expected Goals is deliberately
 * absent: no per-fixture xG is stored anywhere in the backend yet.
 */
export function buildMatchSnapshot({
  teamName,
  perspectiveIsHome,
  homeScore,
  awayScore,
  perspectiveStats,
  opponentStats,
}: {
  teamName: string
  perspectiveIsHome: boolean
  homeScore: number
  awayScore: number
  perspectiveStats?: MatchStats
  opponentStats?: MatchStats
}): MatchSnapshot {
  const goalsFor = perspectiveIsHome ? homeScore : awayScore
  const goalsAgainst = perspectiveIsHome ? awayScore : homeScore
  const result: MatchResult = goalsFor > goalsAgainst ? 'win' : goalsFor < goalsAgainst ? 'loss' : 'draw'
  const btts = homeScore > 0 && awayScore > 0
  const cleanSheet = goalsAgainst === 0

  const stats: SnapshotStatChip[] = [
    { key: 'goals', label: 'Goals', value: String(homeScore + awayScore) },
    { key: 'btts', label: 'BTTS', value: btts ? 'Yes' : 'No' },
  ]
  if (perspectiveStats?.corners !== undefined) {
    stats.push({ key: 'corners', label: 'Corners', value: String(Math.round(perspectiveStats.corners)) })
  }
  if (perspectiveStats?.shots_on_target !== undefined) {
    stats.push({ key: 'shots_on_target', label: 'Shots on Target', value: String(Math.round(perspectiveStats.shots_on_target)) })
  }
  stats.push({ key: 'clean_sheet', label: 'Clean Sheet', value: cleanSheet ? 'Yes' : 'No' })
  if (perspectiveStats?.possession_pct !== undefined) {
    stats.push({ key: 'possession', label: 'Possession', value: `${Math.round(perspectiveStats.possession_pct)}%` })
  }
  if (perspectiveStats?.cards_yellow !== undefined || perspectiveStats?.cards_red !== undefined) {
    const totalCards = (perspectiveStats.cards_yellow ?? 0) + (perspectiveStats.cards_red ?? 0)
    stats.push({ key: 'cards', label: 'Cards', value: String(totalCards) })
  }

  const clauses: string[] = []
  clauses.push(
    result === 'win' ? `${teamName} secured the win` : result === 'loss' ? `${teamName} came away with a loss` : `${teamName} played out a draw`,
  )
  if (cleanSheet) {
    clauses.push('kept a clean sheet, limiting the opponent to nothing')
  } else if (btts) {
    clauses.push('both sides found the net')
  }
  if (perspectiveStats?.corners !== undefined && perspectiveStats.corners >= 8) {
    clauses.push('sustained attacking pressure throughout')
  }
  if (opponentStats?.shots_on_target !== undefined && opponentStats.shots_on_target <= 2) {
    clauses.push('held the opponent to almost nothing on target')
  }
  if (perspectiveStats?.possession_pct !== undefined && perspectiveStats.possession_pct >= 55) {
    clauses.push(`controlled the tempo with ${Math.round(perspectiveStats.possession_pct)}% possession`)
  }

  const summary = `${clauses[0]}${clauses.length > 1 ? ', ' + clauses.slice(1).join(' and ') : ''}.`

  return { result, stats, summary }
}
