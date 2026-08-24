import { Database, Cpu, ShieldCheck, LineChart, PlayCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { IntelligenceCardSkeleton, EngineIdleState, HeroIntelligenceReport } from './intelligence-card'
import type { PublicFeaturedIntelligenceDto } from '@/lib/api/types'

const CAPABILITIES = [
  { icon: Database, title: 'Historical Data', detail: 'Results & statistics analyzed per fixture', color: 'var(--li-cyan)' },
  { icon: Cpu, title: 'Advanced Models', detail: 'Statistical & ML models combined', color: 'var(--li-purple)' },
  { icon: ShieldCheck, title: 'Verified Context', detail: 'Injuries, lineups, news & more', color: 'var(--li-positive)' },
  { icon: LineChart, title: 'Explainable AI', detail: 'Every prediction has a reason', color: 'var(--li-blue)' },
]

/**
 * The hero's right-hand visual is a real currently-published pick when one exists, or an honest
 * neutral platform-state card when it doesn't (shape brief §8: never fabricate a match to fill
 * the space) — rendered through `HeroIntelligenceReport`.
 */
export function HeroSection({ loading, pick }: { loading: boolean; pick: PublicFeaturedIntelligenceDto | null }) {
  return (
    <div className="relative overflow-hidden border-b border-[var(--li-border)]">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.35]"
        style={{
          backgroundImage:
            'radial-gradient(at 15% 10%, rgba(34,211,238,0.10) 0px, transparent 45%), radial-gradient(at 85% 0%, rgba(139,92,246,0.08) 0px, transparent 45%)',
        }}
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            'linear-gradient(to right, var(--li-border) 1px, transparent 1px), linear-gradient(to bottom, var(--li-border) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
        aria-hidden="true"
      />

      <div className="relative mx-auto grid max-w-7xl gap-14 px-6 py-16 lg:grid-cols-[0.95fr_1.2fr] lg:px-10 lg:py-20">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-[var(--li-border)] bg-[var(--li-surface)] px-3 py-1 font-mono text-[11px] uppercase tracking-[0.1em] text-[var(--li-text-secondary)]">
            <span className="size-1.5 rounded-full bg-[var(--li-cyan)]" aria-hidden="true" />
            AI Prediction Intelligence
          </p>

          <h1 className="mt-6 max-w-xl text-4xl font-bold leading-[1.1] tracking-tight text-[var(--li-text-primary)] lg:text-5xl">
            Understand the prediction, <span className="text-[var(--li-cyan)]">not just</span> the prediction.
          </h1>

          <p className="mt-6 max-w-lg text-base leading-relaxed text-[var(--li-text-secondary)] lg:text-lg">
            TitanIQ combines historical data, statistical models, machine learning, and verified
            context into one auditable prediction workflow.
          </p>

          <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {CAPABILITIES.map((c) => (
              <div key={c.title} className="flex flex-col items-start gap-2">
                <span
                  className="flex size-9 items-center justify-center rounded-[var(--li-radius-sm)] border border-[var(--li-border)] bg-[var(--li-surface)]"
                  style={{ color: c.color }}
                >
                  <c.icon className="size-4.5" aria-hidden="true" />
                </span>
                <p className="text-sm font-semibold text-[var(--li-text-primary)]">{c.title}</p>
                <p className="text-xs leading-snug text-[var(--li-text-muted)]">{c.detail}</p>
              </div>
            ))}
          </div>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button
              asChild
              size="lg"
              className="group relative overflow-hidden rounded-[10px] bg-[var(--li-cyan)] text-[var(--li-text-inverse)] shadow-[var(--li-glow-cyan-sm)] transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:bg-[var(--li-cyan-hover)] hover:shadow-[var(--li-glow-cyan)] active:translate-y-0"
            >
              <a href="#proof-of-mechanism">
                <span
                  className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/25 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-full motion-reduce:hidden"
                  aria-hidden="true"
                />
                Explore Predictions
              </a>
            </Button>
            <Button
              asChild
              variant="secondary"
              size="lg"
              className="rounded-[10px] border-[var(--li-border)] bg-[var(--li-surface)] text-[var(--li-text-primary)] transition-colors duration-200 hover:border-[var(--li-border-strong)] hover:bg-[var(--li-surface-elevated)]"
            >
              <a href="#how-it-works">
                <PlayCircle className="size-4" aria-hidden="true" />
                How TitanIQ Works
              </a>
            </Button>
          </div>
        </div>

        <div className="relative">
          <div
            className="pointer-events-none absolute -inset-4 rounded-[var(--li-radius-lg)] opacity-60"
            style={{ background: 'radial-gradient(circle at 30% 20%, rgba(34,211,238,0.08), transparent 60%)' }}
            aria-hidden="true"
          />
          <div
            className="group relative flex min-h-[280px] flex-col rounded-[var(--li-radius-lg)] border border-[var(--li-glass-3-border)] bg-[var(--li-glass-3-bg)] p-5 shadow-[var(--li-shadow-card)] backdrop-blur-[var(--li-glass-3-blur)] transition-[transform,box-shadow,border-color] duration-200 hover:-translate-y-1 hover:border-[var(--li-cyan-strong)] hover:shadow-[var(--li-shadow-card-hover),var(--li-glow-cyan-sm)] lg:p-6"
          >
            {/* A soft inner top highlight — the one place this card reaches for a literal "glass
                edge" cue, restrained to a 1px gradient line rather than a full glossy overlay. */}
            <div
              className="pointer-events-none absolute inset-x-0 top-0 h-px rounded-t-[var(--li-radius-lg)] opacity-60"
              style={{ background: 'linear-gradient(90deg, transparent, rgba(248,250,252,0.35), transparent)' }}
              aria-hidden="true"
            />
            {loading ? <IntelligenceCardSkeleton /> : pick ? <HeroIntelligenceReport pick={pick} /> : <EngineIdleState />}
          </div>
        </div>
      </div>
    </div>
  )
}
