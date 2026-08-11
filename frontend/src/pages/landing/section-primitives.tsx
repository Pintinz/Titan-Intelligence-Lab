import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

export function Section({
  id,
  className,
  children,
}: {
  id?: string
  className?: string
  children: ReactNode
}) {
  return (
    <section id={id} className={cn('mx-auto max-w-6xl px-6 py-16 lg:px-10 lg:py-24', className)}>
      {children}
    </section>
  )
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = 'left',
}: {
  eyebrow: string
  title: string
  description?: string
  align?: 'left' | 'center'
}) {
  return (
    <div className={cn('mb-10 max-w-2xl', align === 'center' && 'mx-auto text-center')}>
      <p className="font-telemetry text-xs font-semibold uppercase tracking-[0.16em] text-accent-primary">
        {eyebrow}
      </p>
      <h2 className="mt-2 font-display text-2xl font-semibold tracking-tight text-text-primary lg:text-3xl">
        {title}
      </h2>
      {description && <p className="mt-3 text-base text-text-secondary">{description}</p>}
    </div>
  )
}

export function Hairline({ className }: { className?: string }) {
  return <div className={cn('h-px w-full bg-border-subtle', className)} aria-hidden="true" />
}
