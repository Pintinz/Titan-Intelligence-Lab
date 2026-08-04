import type { KeyboardEvent } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/cn'
import { DOMAIN_COLOR_VAR, type DomainKey } from '../primitives/badge'

/** Sidebar nav item — a left signal-bar (not a filled background) marks the active
 * route, matching the review-panel's edge-marker vocabulary used by the Intelligence
 * Rail and match cards. */
export function InfinityNavItem({
  icon: Icon,
  label,
  active,
  badge,
}: {
  icon: LucideIcon
  label: string
  active?: boolean
  badge?: string
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2.5 border-l-2 px-3 py-2 font-infinity-body text-[13px] transition-colors duration-150',
        active
          ? 'border-infinity-signal bg-infinity-signal-muted text-infinity-text-primary'
          : 'border-transparent text-infinity-text-secondary hover:bg-infinity-ground-2 hover:text-infinity-text-primary',
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{label}</span>
      {badge && <span className="font-infinity-mono text-[10px] text-infinity-text-muted">{badge}</span>}
    </div>
  )
}

/** Breadcrumbs — chevron-separated, uppercase-tracked to match the label vocabulary
 * used across every other Infinity component (never a plain "/" separator). */
export function InfinityBreadcrumbs({ items }: { items: string[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-1.5">
      {items.map((item, i) => (
        <span key={item} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="size-3 text-infinity-text-muted" aria-hidden="true" />}
          <span
            className={cn(
              'font-infinity-body text-[11px] font-medium uppercase tracking-[0.06em]',
              i === items.length - 1 ? 'text-infinity-text-primary' : 'text-infinity-text-muted',
            )}
          >
            {item}
          </span>
        </span>
      ))}
    </nav>
  )
}

/** Sport Switcher — a horizontal segmented control where each segment carries its
 * sport's domain color as an underline, not a filled pill; switching sports should
 * feel like changing broadcast channel, not toggling a filter. */
export function InfinitySportSwitcher({
  sports,
  active,
  onChange,
}: {
  sports: Array<{ key: Extract<DomainKey, 'football' | 'basketball' | 'baseball' | 'table-tennis'>; label: string }>
  active: string
  onChange: (key: string) => void
}) {
  // ARIA APG tabs pattern: only the active tab sits in the page Tab order (roving
  // tabindex); Left/Right/Home/End move focus *and* selection between tabs — matches
  // what `role="tab"`/`aria-selected` promises a screen reader user, not just the label.
  const activeIndex = Math.max(0, sports.findIndex((s) => s.key === active))

  function focusAndSelect(index: number) {
    const target = sports[(index + sports.length) % sports.length]
    onChange(target.key)
    requestAnimationFrame(() => {
      document.getElementById(`infinity-sport-tab-${target.key}`)?.focus()
    })
  }

  function handleKeyDown(e: KeyboardEvent, index: number) {
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      focusAndSelect(index + 1)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      focusAndSelect(index - 1)
    } else if (e.key === 'Home') {
      e.preventDefault()
      focusAndSelect(0)
    } else if (e.key === 'End') {
      e.preventDefault()
      focusAndSelect(sports.length - 1)
    }
  }

  return (
    <div role="tablist" aria-label="Sport switcher" className="flex gap-1 border-b border-infinity-border-hairline">
      {sports.map((sport, index) => {
        const isActive = sport.key === active
        return (
          <button
            key={sport.key}
            id={`infinity-sport-tab-${sport.key}`}
            role="tab"
            aria-selected={isActive}
            tabIndex={index === activeIndex ? 0 : -1}
            onClick={() => onChange(sport.key)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={cn(
              'relative -mb-px border-b-2 px-3 py-2 font-infinity-body text-[13px] font-medium transition-colors duration-150',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-infinity-signal focus-visible:ring-offset-2 focus-visible:ring-offset-infinity-ground-0',
              isActive ? 'text-infinity-text-primary' : 'border-transparent text-infinity-text-muted hover:text-infinity-text-secondary',
            )}
            style={{ borderColor: isActive ? DOMAIN_COLOR_VAR[sport.key] : 'transparent' }}
          >
            {sport.label}
          </button>
        )
      })}
    </div>
  )
}

/** Header bar shell — the app-wide chrome (logo slot / global search / profile /
 * notifications), visual-only, not wired to real routing or auth state. */
export function InfinityHeaderShell({ children }: { children: React.ReactNode }) {
  return (
    <header className="flex h-14 items-center gap-4 border-b border-infinity-border-hairline bg-infinity-ground-1 px-4">
      {children}
    </header>
  )
}

/** Command Palette shell — visual language only (not wired to a real keyboard listener
 * or router here); a review-panel with a search field and grouped, icon-led results,
 * matching the InfinityNavItem vocabulary rather than a generic list. */
export function InfinityCommandPaletteShell({
  groups,
}: {
  groups: Array<{ label: string; items: Array<{ icon: LucideIcon; label: string; shortcut?: string }> }>
}) {
  return (
    <div className="w-full max-w-md overflow-hidden rounded-infinity-md border border-infinity-border-default bg-infinity-ground-2 shadow-[var(--infinity-elevation-2)]">
      <div className="border-b border-infinity-border-hairline p-3">
        <div className="flex items-center gap-2 rounded-infinity-sm border border-infinity-border-default bg-infinity-ground-0 px-2.5 py-1.5">
          <span className="font-infinity-mono text-[11px] text-infinity-text-muted">Search or run a command…</span>
        </div>
      </div>
      <div className="max-h-72 overflow-y-auto p-2">
        {groups.map((group) => (
          <div key={group.label} className="mb-2 last:mb-0">
            <p className="px-2 py-1 font-infinity-body text-[10px] font-medium uppercase tracking-[0.08em] text-infinity-text-muted">
              {group.label}
            </p>
            {group.items.map((item) => (
              <div key={item.label} className="flex items-center gap-2.5 rounded-infinity-sm px-2 py-1.5 text-infinity-text-secondary hover:bg-infinity-ground-1">
                <item.icon className="size-3.5 shrink-0" aria-hidden="true" />
                <span className="flex-1 font-infinity-body text-[13px]">{item.label}</span>
                {item.shortcut && <kbd className="font-infinity-mono text-[10px] text-infinity-text-muted">{item.shortcut}</kbd>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
