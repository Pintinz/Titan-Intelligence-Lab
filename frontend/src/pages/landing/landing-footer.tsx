import { Link } from 'react-router-dom'
import { BRAND } from '@/components/layout/nav-config'

const COLUMNS = [
  {
    heading: 'Platform',
    links: [
      { label: 'Methodology', href: '/methodology' },
      { label: 'Pricing', href: '/pricing' },
      { label: 'Docs', href: '/docs' },
      { label: 'API Reference', href: '/api-reference' },
    ],
  },
  {
    heading: 'Company',
    links: [
      { label: 'About', href: '/about' },
      { label: 'Contact', href: '/contact' },
    ],
  },
]

export function LandingFooter() {
  return (
    <footer className="border-t border-border-subtle">
      <div className="mx-auto max-w-6xl px-6 py-12 lg:px-10">
        <div className="flex flex-col gap-10 lg:flex-row lg:justify-between">
          <div className="max-w-xs">
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-accent-primary" aria-hidden="true" />
              <span className="font-display text-sm font-semibold text-text-primary">{BRAND.name}</span>
            </div>
            <p className="mt-2 text-sm text-text-secondary">{BRAND.tagline}</p>
          </div>
          <div className="flex gap-16">
            {COLUMNS.map((col) => (
              <div key={col.heading}>
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{col.heading}</p>
                <ul className="mt-3 space-y-2">
                  {col.links.map((link) => (
                    <li key={link.href}>
                      <Link to={link.href} className="text-sm text-text-secondary hover:text-text-primary">
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
        <p className="mt-10 text-xs text-text-muted">
          © {new Date().getFullYear()} Titan Intelligence Labs. TitanIQ is a sports intelligence
          platform, not a betting service.
        </p>
      </div>
    </footer>
  )
}
