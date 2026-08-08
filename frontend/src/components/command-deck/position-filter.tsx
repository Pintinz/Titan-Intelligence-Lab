import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from './primitives/domain'

/** PositionFilter — same shape as `CountryFilter`, grouping key swapped from country to the
 * player's real `position` field. Counts are real per-position tallies of the current sport's
 * already-fetched player list, no refetch on selection. */
export function PositionFilter({
  positionCounts,
  selected,
  onSelect,
  sportDomain,
}: {
  positionCounts: Array<{ position: string; count: number }>
  selected: string | null
  onSelect: (position: string | null) => void
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
}) {
  if (positionCounts.length === 0) return null
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const domainBg = domainTint(sportDomain, 14)
  const totalCount = positionCounts.reduce((sum, p) => sum + p.count, 0)

  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      <Chip label="All positions" count={totalCount} active={selected === null} color={domainColor} bg={domainBg} onClick={() => onSelect(null)} />
      {positionCounts.map(({ position, count }) => (
        <Chip
          key={position}
          label={position}
          count={count}
          active={selected === position}
          color={domainColor}
          bg={domainBg}
          onClick={() => onSelect(selected === position ? null : position)}
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
