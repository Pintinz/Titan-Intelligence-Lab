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

/** Every landing section built from sample data (not live, gated behind auth) wears this. */
export function IllustrativeTag() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border-default px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-text-muted">
      Illustrative
    </span>
  )
}

export function LiveDot() {
  return (
    <span className="relative inline-flex size-1.5">
      <span className="absolute inline-flex size-full animate-ping rounded-full bg-live opacity-60 motion-reduce:animate-none" />
      <span className="relative inline-flex size-1.5 rounded-full bg-live" />
    </span>
  )
}

export function Hairline({ className }: { className?: string }) {
  return <div className={cn('h-px w-full bg-border-subtle', className)} aria-hidden="true" />
}
