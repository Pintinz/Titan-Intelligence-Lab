import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Menu, X } from 'lucide-react'
import { cn } from '@/lib/cn'

const NAV_LINKS = [
  { href: '#featured-intelligence', label: 'Match Intelligence' },
  { href: '#multi-sport', label: 'Sports' },
  { href: '#news-intelligence', label: 'News Intelligence' },
  { href: '#learning-intelligence', label: 'Learning' },
]

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={cn('sticky top-0 z-50 w-full transition-colors duration-300', scrolled ? 'backdrop-blur-md' : '')}
      style={{
        background: scrolled ? 'rgba(6, 8, 13, 0.82)' : 'transparent',
        borderBottom: scrolled ? '1px solid var(--tl-steel-line)' : '1px solid transparent',
      }}
    >
      <nav className="mx-auto flex w-full max-w-[1400px] items-center justify-between px-6 py-4 sm:px-10" aria-label="Primary">
        <Link to="/" className="tl-display flex items-baseline gap-1 text-xl" style={{ color: 'var(--tl-ink)' }}>
          TITAN<span style={{ color: 'var(--tl-signal)' }}>IQ</span>
        </Link>

        <ul className="hidden items-center gap-7 lg:flex">
          {NAV_LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="tl-eyebrow transition-colors hover:opacity-100"
                style={{ color: 'var(--tl-ink-dim)', fontSize: '0.7rem' }}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-3 lg:flex">
          <Link
            to="/login"
            className="tl-eyebrow rounded-md px-4 py-2 transition-colors"
            style={{ color: 'var(--tl-ink)', fontSize: '0.7rem' }}
          >
            Sign in
          </Link>
          <Link
            to="/signup"
            className="tl-eyebrow rounded-md px-4 py-2 transition-colors"
            style={{ background: 'var(--tl-signal)', color: 'var(--tl-void)', fontSize: '0.7rem' }}
          >
            Get Started
          </Link>
        </div>

        <button
          type="button"
          className="flex h-9 w-9 items-center justify-center rounded-md lg:hidden"
          style={{ border: '1px solid var(--tl-steel-line-strong)' }}
          aria-expanded={open}
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? <X className="h-4 w-4" style={{ color: 'var(--tl-ink)' }} /> : <Menu className="h-4 w-4" style={{ color: 'var(--tl-ink)' }} />}
        </button>
      </nav>

      {open && (
        <div
          className="flex flex-col gap-1 px-6 pb-6 lg:hidden"
          style={{ borderTop: '1px solid var(--tl-steel-line)', background: 'var(--tl-void)' }}
        >
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="tl-eyebrow py-3"
              style={{ color: 'var(--tl-ink-dim)' }}
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
          <div className="mt-2 flex flex-col gap-2">
            <Link to="/login" className="tl-eyebrow rounded-md py-2.5 text-center" style={{ border: '1px solid var(--tl-steel-line-strong)', color: 'var(--tl-ink)' }}>
              Sign in
            </Link>
            <Link to="/signup" className="tl-eyebrow rounded-md py-2.5 text-center" style={{ background: 'var(--tl-signal)', color: 'var(--tl-void)' }}>
              Get Started
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}
