import { Link } from 'react-router-dom'
import { BRAND } from './nav-config'
import { FOOTER_COLUMNS, SOCIAL_LINKS, PLATFORM_VERSION } from './marketing-nav-config'
import { BrandIcon } from './brand-icons'

const SOCIAL_ICON_KEYS: Record<string, string> = {
  Facebook: 'facebook',
  Instagram: 'instagram',
  X: 'x',
}

/**
 * Enterprise footer, kept deliberately short — see the comment above `FOOTER_COLUMNS` for where
 * everything not listed here still lives (header mega-menu, Trust Center, About page).
 */
export function SiteFooter() {
  const year = new Date().getFullYear()

  return (
    <footer className="border-t border-border-subtle bg-bg-secondary/20">
      <div className="mx-auto max-w-6xl px-6 py-14 lg:px-10 lg:py-16">
        <div className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-4 lg:grid-cols-12">
          <div className="col-span-2 sm:col-span-4 lg:col-span-4 lg:pr-8">
            <Link to="/" className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-accent-primary" aria-hidden="true" />
              <span className="font-display text-sm font-semibold text-text-primary">{BRAND.name}</span>
            </Link>
            <p className="mt-3 text-sm font-medium text-text-secondary">{BRAND.tagline}</p>
            <p className="mt-2 max-w-xs text-sm leading-relaxed text-text-muted">{BRAND.description}</p>

            <ul className="mt-6 flex items-center gap-3">
              {SOCIAL_LINKS.map((social) => (
                <li key={social.label}>
                  <a
                    href={social.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={social.label}
                    className={[
                      'flex size-9 items-center justify-center rounded-full border border-border-default text-text-muted',
                      'transition-all duration-[var(--motion-duration-fast)] ease-out',
                      'hover:-translate-y-0.5 hover:border-accent-primary/50 hover:text-accent-primary hover:shadow-[0_0_0_1px_var(--color-accent-primary-muted)]',
                      'motion-reduce:hover:translate-y-0',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-primary focus-visible:ring-offset-2 focus-visible:ring-offset-bg-secondary',
                    ].join(' ')}
                  >
                    <BrandIcon name={SOCIAL_ICON_KEYS[social.label]} className="size-4" />
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {FOOTER_COLUMNS.map((column) => (
            <div key={column.label} className="lg:col-span-2">
              <p className="text-xs font-medium uppercase tracking-wide text-text-muted">{column.label}</p>
              <ul className="mt-3 space-y-2">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      to={link.href}
                      className="text-sm text-text-secondary transition-colors duration-[var(--motion-duration-fast)] hover:text-text-primary"
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
              {column.label === 'Legal' && (
                <Link
                  to="/trust-center"
                  className="mt-3 inline-block text-xs font-medium text-accent-primary transition-colors hover:text-accent-primary-hover"
                >
                  View all policies →
                </Link>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-border-subtle">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-6 py-6 text-xs text-text-muted sm:flex-row sm:items-center sm:justify-between lg:px-10">
          <p>© {year} Titan Intelligence Labs. All rights reserved.</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 font-mono">
            <span>{PLATFORM_VERSION}</span>
            <span aria-hidden="true">·</span>
            <Link to="/status" className="inline-flex items-center gap-1.5 transition-colors hover:text-text-primary">
              <span className="size-1.5 rounded-full bg-success" aria-hidden="true" />
              All systems operational
            </Link>
            <span aria-hidden="true">·</span>
            <span className="font-body italic text-text-muted/80">Built with Intelligence.</span>
          </div>
        </div>
      </div>
    </footer>
  )
}
