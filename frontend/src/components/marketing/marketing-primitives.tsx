import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'

export function PageHero({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
}) {
  return (
    <div className="border-b border-border-subtle bg-bg-secondary/30">
      <div className="mx-auto max-w-6xl px-6 py-16 lg:px-10 lg:py-24">
        <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
          {eyebrow}
        </p>
        <h1 className="mt-2 max-w-3xl font-display text-3xl font-semibold tracking-tight text-text-primary lg:text-5xl">
          {title}
        </h1>
        <p className="mt-4 max-w-2xl text-base text-text-secondary lg:text-lg">{description}</p>
        {actions && <div className="mt-8 flex flex-wrap gap-3">{actions}</div>}
      </div>
    </div>
  )
}

export function ValueCard({ icon: Icon, title, description }: { icon: LucideIcon; title: string; description: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-elevated p-5">
      <div className="flex size-9 items-center justify-center rounded-md bg-accent-primary-muted">
        <Icon className="size-4 text-accent-primary" aria-hidden="true" />
      </div>
      <h3 className="mt-4 font-display text-sm font-semibold text-text-primary">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{description}</p>
    </div>
  )
}

export function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-elevated p-5 text-center">
      <p className="font-telemetry text-2xl font-bold text-accent-primary lg:text-3xl">{value}</p>
      <p className="mt-1 text-xs text-text-muted">{label}</p>
    </div>
  )
}

export function ContactCard({
  icon: Icon,
  title,
  description,
  email,
  responseTime,
}: {
  icon: LucideIcon
  title: string
  description: string
  email: string
  responseTime: string
}) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-elevated p-5">
      <div className="flex size-9 items-center justify-center rounded-md bg-accent-primary-muted">
        <Icon className="size-4 text-accent-primary" aria-hidden="true" />
      </div>
      <h3 className="mt-4 font-display text-sm font-semibold text-text-primary">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{description}</p>
      <a href={`mailto:${email}`} className="mt-3 block text-sm font-medium text-accent-primary hover:text-accent-primary-hover">
        {email}
      </a>
      <p className="mt-1 text-xs text-text-muted">{responseTime}</p>
    </div>
  )
}

export function FaqAccordion({ items }: { items: { question: string; answer: ReactNode }[] }) {
  return (
    <div className="divide-y divide-border-subtle rounded-lg border border-border-default bg-bg-elevated">
      {items.map((item, i) => (
        <details key={i} className="group px-5 py-4 open:pb-4">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-display text-sm font-semibold text-text-primary marker:content-none">
            {item.question}
            <span
              className="flex size-5 shrink-0 items-center justify-center rounded-full border border-border-default text-xs text-text-muted transition-transform duration-200 group-open:rotate-45"
              aria-hidden="true"
            >
              +
            </span>
          </summary>
          <div className="mt-2 text-sm leading-relaxed text-text-secondary">{item.answer}</div>
        </details>
      ))}
    </div>
  )
}

export function PricingTierCard({
  name,
  price,
  period,
  description,
  features,
  cta,
  ctaHref,
  featured = false,
}: {
  name: string
  price: string
  period?: string
  description: string
  features: string[]
  cta: string
  ctaHref: string
  featured?: boolean
}) {
  return (
    <div
      className={cn(
        'relative flex flex-col rounded-lg border p-6',
        featured ? 'border-accent-primary bg-bg-elevated shadow-elevation-2' : 'border-border-default bg-bg-elevated',
      )}
    >
      {featured && (
        <span className="absolute -top-3 left-6 rounded-full bg-accent-primary px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-bg-primary">
          Most popular
        </span>
      )}
      <h3 className="font-display text-lg font-semibold text-text-primary">{name}</h3>
      <p className="mt-1 text-sm text-text-secondary">{description}</p>
      <div className="mt-5 flex items-baseline gap-1">
        <span className="font-display text-3xl font-bold text-text-primary">{price}</span>
        {period && <span className="text-sm text-text-muted">{period}</span>}
      </div>
      <ul className="mt-6 flex-1 space-y-2.5">
        {features.map((feature) => (
          <li key={feature} className="flex items-start gap-2 text-sm text-text-secondary">
            <span className="mt-1.5 size-1 shrink-0 rounded-full bg-accent-primary" aria-hidden="true" />
            {feature}
          </li>
        ))}
      </ul>
      <Button asChild variant={featured ? 'primary' : 'secondary'} className="mt-6 w-full">
        <Link to={ctaHref}>{cta}</Link>
      </Button>
    </div>
  )
}

export function TimelineStep({
  status,
  title,
  description,
  eta,
}: {
  status: 'shipped' | 'in-progress' | 'planned'
  title: string
  description: string
  eta?: string
}) {
  const statusConfig = {
    shipped: { label: 'Shipped', className: 'bg-success-muted text-success border-success/30' },
    'in-progress': { label: 'In progress', className: 'bg-accent-primary-muted text-accent-primary border-accent-primary/30' },
    planned: { label: 'Planned', className: 'bg-bg-secondary text-text-muted border-border-default' },
  }[status]

  return (
    <div className="flex gap-4 border-b border-border-subtle py-5 last:border-0">
      <div className="w-28 shrink-0">
        <span className={cn('inline-block rounded-full border px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide', statusConfig.className)}>
          {statusConfig.label}
        </span>
      </div>
      <div className="flex-1">
        <h3 className="font-display text-sm font-semibold text-text-primary">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-text-secondary">{description}</p>
        {eta && <p className="mt-1.5 text-xs text-text-muted">Target: {eta}</p>}
      </div>
    </div>
  )
}

export function StatusRow({
  name,
  status,
  uptime,
}: {
  name: string
  status: 'operational' | 'degraded' | 'outage'
  uptime: string
}) {
  const statusConfig = {
    operational: { label: 'Operational', dot: 'bg-success', text: 'text-success' },
    degraded: { label: 'Degraded performance', dot: 'bg-warning', text: 'text-warning' },
    outage: { label: 'Outage', dot: 'bg-danger', text: 'text-danger' },
  }[status]

  return (
    <div className="flex items-center justify-between border-b border-border-subtle py-3.5 last:border-0">
      <div className="flex items-center gap-3">
        <span className={cn('size-2 rounded-full', statusConfig.dot)} aria-hidden="true" />
        <span className="text-sm font-medium text-text-primary">{name}</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="font-mono text-xs text-text-muted">{uptime} uptime</span>
        <span className={cn('text-xs font-medium', statusConfig.text)}>{statusConfig.label}</span>
      </div>
    </div>
  )
}

export function TeamPrincipleCard({ number, title, description }: { number: string; title: string; description: string }) {
  return (
    <div className="flex gap-4">
      <span className="font-telemetry text-lg font-bold text-accent-primary/50">{number}</span>
      <div>
        <h3 className="font-display text-sm font-semibold text-text-primary">{title}</h3>
        <p className="mt-1 text-sm leading-relaxed text-text-secondary">{description}</p>
      </div>
    </div>
  )
}

export function DocCard({ icon: Icon, title, description, href }: { icon: LucideIcon; title: string; description: string; href: string }) {
  return (
    <Link
      to={href}
      className="group flex flex-col rounded-lg border border-border-default bg-bg-elevated p-5 transition-all duration-200 hover:border-accent-primary/50 hover:shadow-elevation-2"
    >
      <div className="flex size-9 items-center justify-center rounded-md bg-accent-primary-muted">
        <Icon className="size-4 text-accent-primary" aria-hidden="true" />
      </div>
      <h3 className="mt-4 font-display text-sm font-semibold text-text-primary group-hover:text-accent-primary">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-text-secondary">{description}</p>
    </Link>
  )
}
