import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TeamMonogramBadge } from '@/components/domain/team-monogram-badge'

describe('TeamMonogramBadge', () => {
  it('renders initials from a multi-word name', () => {
    render(<TeamMonogramBadge id="team-1" name="Manchester City" />)
    expect(screen.getByText('MC')).toBeInTheDocument()
  })

  it('renders the same color for the same id (deterministic)', () => {
    const { container: a } = render(<TeamMonogramBadge id="team-1" name="Arsenal" />)
    const { container: b } = render(<TeamMonogramBadge id="team-1" name="Arsenal" />)
    const styleA = (a.firstChild as HTMLElement).style.backgroundColor
    const styleB = (b.firstChild as HTMLElement).style.backgroundColor
    expect(styleA).toBe(styleB)
  })
})
