import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type CDButtonVariant = 'primary' | 'secondary'
type CDButtonSize = 'sm' | 'md'

interface CDButtonOwnProps {
  variant?: CDButtonVariant
  size?: CDButtonSize
  icon?: ReactNode
  children: ReactNode
  className?: string
}

type CDButtonProps = CDButtonOwnProps &
  ({ href: string; onClick?: never } | { href?: never; onClick: () => void; type?: 'button' | 'submit' })

const SIZE_CLASSES: Record<CDButtonSize, string> = {
  sm: 'h-8 px-3 text-[12px] gap-1.5',
  md: 'h-10 px-4 text-[13px] gap-2',
}

/**
 * CDButton — the one primary/secondary button shape for Command Deck, replacing the inline-
 * styled `<Link>`/`<button>` pairs that had drifted slightly across Discovery, AI Picks, and
 * Mission Control. Primary: soft indigo gradient + real shadow + hover lift (`--cd-btn-primary-*`
 * tokens). Secondary: glass surface + outline + hover glow, never competing with primary for
 * attention. Polymorphic on `href` (renders a router `Link`) vs `onClick` (renders a `button`) so
 * call sites don't need to know which element they're getting.
 */
export function CDButton({ variant = 'secondary', size = 'md', icon, children, className = '', ...rest }: CDButtonProps) {
  const base = `inline-flex shrink-0 items-center justify-center rounded-[var(--cd-radius-md)] font-[var(--cd-font-body)] font-semibold transition-all duration-[var(--cd-motion-base)] ease-out ${SIZE_CLASSES[size]} ${className}`

  const style =
    variant === 'primary'
      ? {
          backgroundImage: 'var(--cd-btn-primary-bg)',
          color: 'var(--cd-text-inverse)',
          boxShadow: 'var(--cd-btn-primary-shadow)',
        }
      : {
          backgroundColor: 'color-mix(in srgb, var(--cd-surface-2) 70%, transparent)',
          backdropFilter: 'blur(var(--cd-card-blur))',
          border: '1px solid var(--cd-border-default)',
          color: 'var(--cd-text-secondary)',
        }

  const hoverClass =
    variant === 'primary'
      ? 'hover:-translate-y-0.5 hover:shadow-[var(--cd-btn-primary-shadow-hover)]'
      : 'hover:-translate-y-0.5 hover:border-[var(--cd-accent)] hover:text-[var(--cd-accent)] hover:shadow-[var(--cd-glow-accent)]'

  const content = (
    <>
      {icon}
      {children}
    </>
  )

  if ('href' in rest && rest.href) {
    return (
      <Link to={rest.href} className={`${base} ${hoverClass}`} style={style}>
        {content}
      </Link>
    )
  }

  const { onClick, type = 'button' } = rest as Extract<CDButtonProps, { onClick: () => void }>
  return (
    <button type={type} onClick={onClick} className={`${base} ${hoverClass}`} style={style}>
      {content}
    </button>
  )
}
