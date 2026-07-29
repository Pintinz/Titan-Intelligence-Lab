import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/theme-toggle'
import { cn } from '@/lib/cn'

const MARKETING_LINKS = [
  { to: '/pricing', label: 'Pricing' },
  { to: '/methodology', label: 'Methodology' },
  { to: '/docs', label: 'Docs' },
  { to: '/api-reference', label: 'API' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
]

/** Shared header/footer chrome for the public marketing site — landing + the honest-content-only
 * pages (pricing/methodology/docs/api-reference/about/contact). Auth pages (login/signup/...)
 * intentionally do NOT use this shell — they keep their own centered-card layout (Phase 4). */
export function MarketingShell() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-svh flex-col bg-bg-primary">
      <header className="sticky top-0 z-40 border-b border-border-subtle bg-bg-glass backdrop-blur-[var(--blur-glass-md)]">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link to="/" className="font-display text-lg font-semibold text-text-primary">
            TitanIQ
          </Link>

          <nav className="hidden items-center gap-6 lg:flex">
            {MARKETING_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  cn(
                    'text-sm text-text-secondary transition-colors hover:text-text-primary',
                    isActive && 'text-text-primary',
                  )
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden items-center gap-3 lg:flex">
            <ThemeToggle />
            <Button asChild variant="secondary" size="sm">
              <Link to="/login">Sign in</Link>
            </Button>
          </div>

          <button
            type="button"
            className="text-text-secondary lg:hidden"
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            onClick={() => setMobileOpen((open) => !open)}
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>

        {mobileOpen && (
          <nav className="flex flex-col gap-1 border-t border-border-subtle px-6 py-4 lg:hidden">
            {MARKETING_LINKS.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                onClick={() => setMobileOpen(false)}
                className="rounded-md px-2 py-2 text-sm text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
              >
                {link.label}
              </NavLink>
            ))}
            <Link
              to="/login"
              onClick={() => setMobileOpen(false)}
              className="mt-2 rounded-md bg-accent-primary px-2 py-2 text-center text-sm font-medium text-text-inverse"
            >
              Sign in
            </Link>
          </nav>
        )}
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <MarketingFooter />
    </div>
  )
}

function MarketingFooter() {
  return (
    <footer className="border-t border-border-subtle">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 sm:flex-row sm:justify-between">
        <div>
          <p className="font-display text-base font-semibold text-text-primary">TitanIQ</p>
          <p className="mt-1 max-w-xs text-sm text-text-muted">
            Calibrated, explainable, model-driven sports intelligence — Football, Basketball,
            Baseball, and Table Tennis.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-x-12 gap-y-2 text-sm sm:grid-cols-3">
          {MARKETING_LINKS.map((link) => (
            <Link key={link.to} to={link.to} className="text-text-secondary hover:text-text-primary">
              {link.label}
            </Link>
          ))}
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-6 pb-8 text-xs text-text-muted">
        © {new Date().getFullYear()} TitanIQ. All predictions are probabilistic estimates, not
        betting advice.
      </div>
    </footer>
  )
}
