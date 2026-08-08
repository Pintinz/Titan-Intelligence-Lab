import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from './primitives/domain'

/** SeasonFilter — same shape as `CountryFilter`/`PositionFilter`, grouping key swapped to the
 * calendar year a fixture's real `scheduled_at` falls in. A team's fixture history reads as
 * seasons, not an endless chronological scroll — one chip per year, real per-year tallies of the
 * already-fetched fixture list, no refetch on selection. */
export function SeasonFilter({
  seasonCounts,
  selected,
  onSelect,
  sportDomain,
}: {
  seasonCounts: Array<{ key: string; label: string; count: number }>
  selected: string | null
  onSelect: (key: string | null) => void
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
}) {
  if (seasonCounts.length === 0) return null
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const domainBg = domainTint(sportDomain, 14)
  const totalCount = seasonCounts.reduce((sum, s) => sum + s.count, 0)

  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      <Chip label="All" count={totalCount} active={selected === null} color={domainColor} bg={domainBg} onClick={() => onSelect(null)} />
      {seasonCounts.map(({ key, label, count }) => (
        <Chip
          key={key}
          label={label}
          count={count}
          active={selected === key}
          color={domainColor}
          bg={domainBg}
          onClick={() => onSelect(selected === key ? null : key)}
        />
      ))}
    </div>
  )
}

function Chip({
  label,
  count,
  active,
  color,
  bg,
  onClick,
}: {
  label: string
  count: number
  active: boolean
  color: string
  bg: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border py-1.5 pl-2.5 pr-2 font-[var(--cd-font-body)] text-[12px] font-medium transition-colors duration-[var(--cd-motion-base)]"
      style={{
        borderColor: active ? color : 'var(--cd-border-default)',
        backgroundColor: active ? bg : 'var(--cd-surface-2)',
        color: active ? color : 'var(--cd-text-secondary)',
      }}
    >
      <span className="whitespace-nowrap">{label}</span>
      <span
        className="rounded-full px-1.5 py-0.5 font-[var(--cd-font-tabular)] text-[10px] tabular-nums"
        style={{ backgroundColor: 'var(--cd-surface-3)', color: 'var(--cd-text-muted)' }}
      >
        {count}
      </span>
    </button>
  )
}
