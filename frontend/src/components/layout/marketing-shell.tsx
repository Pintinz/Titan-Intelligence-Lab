import { Link, Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { BRAND } from './nav-config'

const LINKS = [
  { label: 'Methodology', href: '/methodology' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Docs', href: '/docs' },
  { label: 'About', href: '/about' },
]

export function MarketingShell() {
  return (
    <div className="flex min-h-svh flex-col bg-bg-primary">
      <header className="flex h-16 items-center gap-6 border-b border-border-subtle px-6 lg:px-10">
        <Link to="/" className="flex items-center gap-2">
          <span className="size-2 rounded-full bg-accent-primary" aria-hidden="true" />
          <span className="font-display text-sm font-semibold tracking-tight text-text-primary">
            {BRAND.name}
          </span>
        </Link>
        <nav className="hidden flex-1 items-center gap-6 md:flex" aria-label="Marketing">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              to={link.href}
              className="text-sm text-text-secondary transition-colors hover:text-text-primary"
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 md:ml-0">
          <Button asChild variant="ghost" size="sm">
            <Link to="/login">Log in</Link>
          </Button>
          <Button asChild size="sm">
            <Link to="/signup">Sign up</Link>
          </Button>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-border-subtle px-6 py-8 text-center text-xs text-text-muted lg:px-10">
        © {new Date().getFullYear()} Titan Intelligence Labs. {BRAND.tagline}
      </footer>
    </div>
  )
}
