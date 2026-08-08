import type { ComponentType, CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { CDButton } from '../primitives/button'
import { CD_DOMAIN_COLOR_VAR, domainTint, type DomainKey } from '../primitives/domain'

type IconComponent = ComponentType<{ className?: string; style?: CSSProperties; 'aria-hidden'?: boolean | 'true' | 'false' }>

/** Shared Command Deck section header for Mission Control — a visual anchor per section: an
 * optional glass icon badge, a stronger display title, an optional supporting subtitle, and a
 * "View all" action. Icon/subtitle are opt-in so a section with nothing meaningful to add above
 * its title (a pure status rail) can skip them without an empty slot. */
export function MissionSection({
  id,
  title,
  subtitle,
  icon,
  domain,
  status,
  viewAllHref,
  children,
}: {
  id?: string
  title: string
  subtitle?: string
  icon?: ReactNode
  /** Tints the icon badge with a category hue from the domain wheel instead of the generic
   * indigo accent — a section whose content is genuinely one category (predictions, learning,
   * a specific sport) reads as that category at a glance. Omitted for sections that are
   * cross-category by nature (mixed sports/entity types) or that already carry their own status
   * color (Live Intelligence's live-red dot) — those stay on the neutral indigo badge. */
  domain?: DomainKey
  status?: ReactNode
  viewAllHref?: string
  children: ReactNode
}) {
  const iconColor = domain ? CD_DOMAIN_COLOR_VAR[domain] : 'var(--cd-accent)'
  const iconBg = domain ? domainTint(domain, 14) : 'var(--cd-accent-muted)'
  const iconRing = domain ? domainTint(domain, 32) : 'var(--cd-accent-strong)'
  return (
    <section id={id} className="scroll-mt-24">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div className="flex items-center gap-3">
          {icon && (
            <span
              className="flex size-9 shrink-0 items-center justify-center rounded-[var(--cd-radius-md)]"
              style={{ backgroundColor: iconBg, color: iconColor, boxShadow: `0 0 0 1px ${iconRing} inset` }}
              aria-hidden="true"
            >
              {icon}
            </span>
          )}
          <div>
            <div className="flex items-center gap-2.5">
              <h3
                className="font-[var(--cd-font-display)] text-[21px] font-semibold leading-tight tracking-[-0.01em] sm:text-[23px]"
                style={{ color: 'var(--cd-text-primary)' }}
              >
                {title}
              </h3>
              {status}
            </div>
            {subtitle && (
              <p className="mt-0.5 font-[var(--cd-font-body)] text-[13px]" style={{ color: 'var(--cd-text-muted)' }}>
                {subtitle}
              </p>
            )}
          </div>
        </div>
        {viewAllHref && (
          <Link
            to={viewAllHref}
            className="group inline-flex shrink-0 items-center gap-1 font-[var(--cd-font-body)] text-[12.5px] font-semibold transition-colors"
            style={{ color: 'var(--cd-accent)' }}
          >
            View all
            <ArrowRight className="size-3.5 transition-transform duration-[var(--cd-motion-base)] group-hover:translate-x-0.5" aria-hidden="true" />
          </Link>
        )}
      </div>
      {children}
    </section>
  )
}

export function MissionCardGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
}

export function MissionSkeletonGrid({ count = 3 }: { count?: number }) {
  return (
    <MissionCardGrid>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-44 animate-pulse rounded-[var(--cd-radius-2xl)] motion-reduce:animate-none"
          style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-card-border)' }}
        />
      ))}
    </MissionCardGrid>
  )
}

/** Premium empty state — never a bare "no X" sentence. A soft pulsing glass icon ring, a
 * friendly explanation, and (when the section has somewhere real to send the user) a primary
 * action — never a fabricated action when nothing real exists to link to. */
export function MissionEmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  actionHref,
}: {
  icon?: IconComponent
  title: string
  description: string
  actionLabel?: string
  actionHref?: string
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-[var(--cd-radius-2xl)] p-10 text-center"
      style={{ background: 'var(--cd-card-surface)', border: '1px solid var(--cd-border-hairline)' }}
    >
      {Icon && (
        <span className="relative flex size-14 items-center justify-center">
          <span
            className="animate-hero-glow motion-reduce:animate-none absolute inset-0 rounded-full"
            style={{ backgroundColor: 'var(--cd-accent-muted)' }}
            aria-hidden="true"
          />
          <span
            className="relative flex size-11 items-center justify-center rounded-full"
            style={{ backgroundColor: 'var(--cd-surface-2)', boxShadow: '0 0 0 1px var(--cd-border-default) inset' }}
          >
            <Icon className="size-5" style={{ color: 'var(--cd-accent)' }} aria-hidden="true" />
          </span>
        </span>
      )}
      <div>
        <p className="font-[var(--cd-font-body)] text-[14px] font-semibold" style={{ color: 'var(--cd-text-secondary)' }}>
          {title}
        </p>
        <p className="mx-auto mt-1 max-w-sm font-[var(--cd-font-body)] text-[13px] leading-relaxed" style={{ color: 'var(--cd-text-muted)' }}>
          {description}
        </p>
      </div>
      {actionLabel && actionHref && (
        <CDButton variant="secondary" size="sm" href={actionHref} className="mt-1">
          {actionLabel}
        </CDButton>
      )}
    </div>
  )
}
