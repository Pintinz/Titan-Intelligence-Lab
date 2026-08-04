/** Date-range helpers for the Matches discovery surfaces (Today/Tomorrow/This week sections and
 * their View All pages). Computed in UTC to match the backend's `_fixture_in_date_range`, which
 * compares against `now`'s UTC date — using local-timezone dates here would drift near midnight. */

function toIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function addDays(days: number): Date {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() + days)
  return d
}

export interface DateRange {
  from: string
  to: string
}

export function todayRange(): DateRange {
  const iso = toIsoDate(addDays(0))
  return { from: iso, to: iso }
}

export function tomorrowRange(): DateRange {
  const iso = toIsoDate(addDays(1))
  return { from: iso, to: iso }
}

/** The remainder of the 7-day window after Today/Tomorrow, so the three sections never overlap. */
export function thisWeekRange(): DateRange {
  return { from: toIsoDate(addDays(2)), to: toIsoDate(addDays(6)) }
}
