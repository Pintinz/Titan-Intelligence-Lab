import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { BRAND } from '@/components/layout/nav-config'

const LINKS = [
  { label: 'Methodology', href: '/methodology' },
  { label: 'Pricing', href: '/pricing' },
  { label: 'Docs', href: '/docs' },
]

export function LandingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-border-subtle/60 bg-bg-primary/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-6 lg:px-10">
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
            <Link to="/signup">Sign up free</Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
