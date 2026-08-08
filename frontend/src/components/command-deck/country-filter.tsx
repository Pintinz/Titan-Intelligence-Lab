import { countryFlag } from '@/lib/country-flags'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from './primitives/domain'

/** CountryFilter — a second filter row, entirely client-side over the sport's already-fetched
 * team list (no refetch on selection). Counts are real per-country tallies of the current sport's
 * teams, not a fabricated coverage metric. */
export function CountryFilter({
  countryCounts,
  selected,
  onSelect,
  sportDomain,
}: {
  countryCounts: Array<{ country: string; count: number }>
  selected: string | null
  onSelect: (country: string | null) => void
  sportDomain: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>
}) {
  if (countryCounts.length === 0) return null
  const domainColor = CD_DOMAIN_COLOR_VAR[sportDomain]
  const domainBg = domainTint(sportDomain, 14)
  const totalCount = countryCounts.reduce((sum, c) => sum + c.count, 0)

  return (
    <div className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      <Chip label="All countries" count={totalCount} flag={null} active={selected === null} color={domainColor} bg={domainBg} onClick={() => onSelect(null)} />
      {countryCounts.map(({ country, count }) => (
        <Chip
          key={country}
          label={country}
          count={count}
          flag={countryFlag(country)}
          active={selected === country}
          color={domainColor}
          bg={domainBg}
          onClick={() => onSelect(selected === country ? null : country)}
        />
      ))}
    </div>
  )
}

function Chip({
  label,
  count,
  flag,
  active,
  color,
  bg,
  onClick,
}: {
  label: string
  count: number
  flag: string | null
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
      {flag && <span aria-hidden="true">{flag}</span>}
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
