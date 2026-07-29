import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Section } from '@/pages/landing/telemetry'

export function CtaSection() {
  return (
    <Section className="pt-0">
      <div
        className="relative overflow-hidden rounded-2xl px-8 py-16 text-center sm:px-16"
        style={{ background: 'linear-gradient(135deg, var(--tl-carbon-raised) 0%, var(--tl-carbon) 100%)', border: '1px solid var(--tl-steel-line)' }}
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(ellipse 60% 80% at 50% 0%, rgba(23,230,184,0.12), transparent)' }}
        />
        <h2 className="tl-display relative mx-auto max-w-2xl text-4xl uppercase leading-[0.95] sm:text-5xl" style={{ color: 'var(--tl-ink)' }}>
          See every match through intelligence.
        </h2>
        <p className="relative mx-auto mt-4 max-w-md text-sm" style={{ color: 'var(--tl-ink-dim)' }}>
          Free tier included. No credit card, no betting-board noise — just explainable intelligence.
        </p>
        <Link
          to="/signup"
          className="tl-eyebrow relative mt-8 inline-flex items-center gap-2 rounded-md px-7 py-3.5 transition-transform hover:-translate-y-0.5"
          style={{ background: 'var(--tl-signal)', color: 'var(--tl-void)' }}
        >
          Get Started Free
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </Section>
  )
}
