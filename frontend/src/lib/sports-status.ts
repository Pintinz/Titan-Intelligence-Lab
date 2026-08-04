export function isLiveStatus(status: string): boolean {
  const s = status.toLowerCase()
  return s === 'live' || s === 'in_play'
}

export function fixtureCardStatus(status: string): 'live' | 'upcoming' | 'completed' {
  if (isLiveStatus(status)) return 'live'
  return status.toLowerCase() === 'completed' ? 'completed' : 'upcoming'
}

/** Extracts final-score numbers out of a fixture's `final_state` bag — `undefined` (not `null`)
 * when either side is unknown, matching InfinityMatchCard's `homeScore?`/`awayScore?` props so
 * an unplayed/scoreless fixture renders the card's "–" placeholder instead of `null`. */
export function fixtureScores(finalState: { home: number | null; away: number | null } | null): {
  homeScore: number | undefined
  awayScore: number | undefined
} {
  return {
    homeScore: finalState?.home ?? undefined,
    awayScore: finalState?.away ?? undefined,
  }
}

/** A human countdown to kickoff, computed from a fixture's own real scheduled_at — null once
 * kickoff has passed (nothing to count down to for a live or completed match). */
export function countdownLabel(scheduledAt: string): string | null {
  const diffMs = new Date(scheduledAt).getTime() - Date.now()
  if (diffMs <= 0) return null
  const days = Math.floor(diffMs / 86_400_000)
  const hours = Math.floor((diffMs % 86_400_000) / 3_600_000)
  if (days > 0) return `${days}d ${hours}h`
  const minutes = Math.floor((diffMs % 3_600_000) / 60_000)
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}
