import { Link } from 'react-router-dom'
import { Hairline } from '@/pages/landing/telemetry'

export function LandingFooter() {
  return (
    <footer className="mx-auto w-full max-w-[1400px] px-6 pb-10 pt-6 sm:px-10">
      <Hairline className="mb-8" />
      <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
        <span className="tl-display text-lg" style={{ color: 'var(--tl-ink)' }}>
          TITAN<span style={{ color: 'var(--tl-signal)' }}>IQ</span>
        </span>
        <nav className="flex flex-wrap gap-x-6 gap-y-2" aria-label="Footer">
          {[
            ['About', '/about'],
            ['Methodology', '/methodology'],
            ['Pricing', '/pricing'],
            ['API Reference', '/api-reference'],
            ['Docs', '/docs'],
            ['Contact', '/contact'],
          ].map(([label, href]) => (
            <Link key={href} to={href} className="text-xs" style={{ color: 'var(--tl-ink-faint)' }}>
              {label}
            </Link>
          ))}
        </nav>
        <span className="tl-mono text-xs" style={{ color: 'var(--tl-ink-faint)' }}>
          © {new Date().getFullYear()} Titan Intelligence Labs
        </span>
      </div>
    </footer>
  )
}
