import { Link } from 'react-router-dom'
import { ArrowRight, Play } from 'lucide-react'
import { TICKER_ITEMS } from '@/pages/landing/sample-data'
import { ConfidenceTelemetry, Eyebrow, IllustrativeTag, LiveDot } from '@/pages/landing/telemetry'

/**
 * Hero Intelligence — the thesis of the whole page. Broadcast-open energy (F1 pre-race graphics
 * package): oversized condensed headline, a live-status readout, and a telemetry ticker doing the
 * work a hero stat card usually does — showing the product thinking rather than describing it.
 */
export function HeroSection() {
  const doubled = [...TICKER_ITEMS, ...TICKER_ITEMS]

  return (
    <div className="relative overflow-hidden">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 80% 50% at 50% -10%, rgba(23,230,184,0.14), transparent), radial-gradient(ellipse 60% 40% at 90% 10%, rgba(155,140,255,0.10), transparent)',
        }}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            'linear-gradient(var(--tl-steel-line) 1px, transparent 1px), linear-gradient(90deg, var(--tl-steel-line) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      <div className="relative mx-auto flex w-full max-w-[1400px] flex-col gap-10 px-6 pb-16 pt-16 sm:px-10 sm:pb-24 sm:pt-24">
        <div className="flex items-center gap-3">
          <LiveDot />
          <Eyebrow>Sports Intelligence Platform · Football · Basketball · Baseball · Table Tennis</Eyebrow>
        </div>

        <div className="flex flex-col gap-6">
          <h1
            className="tl-display max-w-4xl text-[13vw] uppercase leading-[0.92] sm:text-6xl md:text-7xl lg:text-8xl"
            style={{ color: 'var(--tl-ink)' }}
          >
            See every match
            <br />
            through <span style={{ color: 'var(--tl-signal)' }}>intelligence</span>.
          </h1>
          <p className="max-w-xl text-base sm:text-lg" style={{ color: 'var(--tl-ink-dim)' }}>
            TitanIQ isn't a betting board or a stats dashboard. It's an explainable intelligence
            engine that reads form, news, community signal, and knowledge graph context, then tells
            you exactly why — with a confidence score that means something.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <Link
            to="/signup"
            className="tl-eyebrow flex items-center gap-2 rounded-md px-6 py-3.5 transition-transform hover:-translate-y-0.5"
            style={{ background: 'var(--tl-signal)', color: 'var(--tl-void)' }}
          >
            Explore Intelligence
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <a
            href="#learning-intelligence"
            className="tl-eyebrow flex items-center gap-2 rounded-md px-6 py-3.5 transition-colors"
            style={{ border: '1px solid var(--tl-steel-line-strong)', color: 'var(--tl-ink)' }}
          >
            <Play className="h-3.5 w-3.5" aria-hidden="true" />
            Watch it think
          </a>
        </div>

        {/* Telemetry ticker — F1 timing-tower / Bloomberg-tape hybrid; a live product readout, not
            decoration. Marquee pauses on hover/focus and is fully static under reduced motion. */}
        <div className="mt-4 flex items-center gap-3">
          <div
            className="relative flex-1 overflow-hidden rounded-md py-3"
            style={{ background: 'var(--tl-carbon)', border: '1px solid var(--tl-steel-line)' }}
          >
            <div className="tl-marquee-track flex w-max gap-8 px-4">
              {doubled.map((item, i) => (
                <div key={i} className="flex shrink-0 items-center gap-3 whitespace-nowrap">
                  <span className="tl-eyebrow" style={{ color: 'var(--tl-ink-faint)', fontSize: '0.65rem' }}>
                    {item.label}
                  </span>
                  <ConfidenceTelemetry composite={item.composite} size="sm" />
                </div>
              ))}
            </div>
          </div>
          <IllustrativeTag className="hidden shrink-0 sm:inline-flex" />
        </div>
      </div>
    </div>
  )
}
