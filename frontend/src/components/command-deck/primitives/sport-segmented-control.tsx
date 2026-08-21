import { useAvailableSports, type SportMeta } from '@/lib/hooks/use-sport'
import { CD_DOMAIN_COLOR_VAR, domainTint, sportDomainFor } from './domain'

/**
 * SportSegmentedControl — the one sport switcher for Command Deck, shared by Competition Center
 * and Team Intelligence rather than two near-identical copies. Text + domain-color tint, never
 * emoji: lucide has no dedicated football/basketball/baseball/table-tennis icons, and no
 * Command Deck surface has used emoji anywhere this design system has shipped — reaching for one
 * here for the first time would be a new, unreviewed convention, not a continuation of one.
 * Horizontally scrollable (`overflow-x-auto`, children `shrink-0`) rather than wrapping or
 * shrinking text, so four segments never clip off-screen on narrow viewports.
 */
export function SportSegmentedControl({ sport, onSportChange }: { sport: SportMeta; onSportChange: (sport: SportMeta) => void }) {
  const availableSports = useAvailableSports()
  return (
    <div
      role="tablist"
      aria-label="Sport"
      className="-mx-1 flex w-fit max-w-full gap-1 overflow-x-auto rounded-[var(--cd-radius-md)] border p-1 backdrop-blur-md"
      style={{ borderColor: 'var(--cd-border-default)', backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 70%, transparent)' }}
    >
      {availableSports.map((s) => {
        const active = s.slug === sport.slug
        const domain = sportDomainFor(s.slug)
        const color = active && domain ? CD_DOMAIN_COLOR_VAR[domain] : active ? 'var(--cd-text-inverse)' : 'var(--cd-text-secondary)'
        return (
          <button
            key={s.slug}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSportChange(s)}
            className="shrink-0 rounded-[var(--cd-radius-sm)] px-3.5 py-1.5 font-[var(--cd-font-body)] text-[12.5px] font-semibold transition-all duration-[var(--cd-motion-base)]"
            style={{
              backgroundColor: active ? (domain ? domainTint(domain, 16) : 'var(--cd-accent-muted)') : 'transparent',
              boxShadow: active ? `0 0 0 1px ${domain ? domainTint(domain, 40) : 'var(--cd-accent-strong)'} inset` : 'none',
              color,
            }}
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}
