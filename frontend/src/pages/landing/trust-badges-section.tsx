import { Link } from 'react-router-dom'
import { Eye, ShieldCheck, UserCheck, Lock } from 'lucide-react'
import { Section } from './section-primitives'

// Every claim here links to the real policy page that backs it — no badge without a document.
const BADGES = [
  { icon: Eye, title: 'Transparent Models', detail: 'No black-box predictions', href: '/methodology' },
  { icon: ShieldCheck, title: 'Auditable & Verifiable', detail: 'Every prediction is traceable', href: '/trust-center' },
  { icon: UserCheck, title: 'Responsible AI', detail: 'Built for responsible use', href: '/responsible-ai' },
  { icon: Lock, title: 'Security First', detail: 'Your data is protected', href: '/security-policy' },
]

export function TrustBadgesSection() {
  return (
    <Section className="border-b border-[var(--li-border)] py-10 lg:py-12">
      <div className="rounded-[var(--li-radius-md)] border border-[var(--li-glass-1-border)] bg-[var(--li-glass-1-bg)] p-6 backdrop-blur-[var(--li-glass-1-blur)]">
        <p className="mb-6 text-xs font-semibold uppercase tracking-wider text-[var(--li-text-muted)]">
          Trusted by smart predictors
        </p>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {BADGES.map((badge) => (
            <Link key={badge.title} to={badge.href} className="group flex items-center gap-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-full border border-[var(--li-border)] bg-[var(--li-surface-elevated)] text-[var(--li-purple)] transition-colors group-hover:border-[var(--li-purple)]">
                <badge.icon className="size-4.5" aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--li-text-primary)]">{badge.title}</p>
                <p className="truncate text-xs text-[var(--li-text-muted)]">{badge.detail}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </Section>
  )
}
