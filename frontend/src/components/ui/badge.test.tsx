import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from '@/components/ui/badge'

describe('Badge', () => {
  it('renders its label', () => {
    render(<Badge>production</Badge>)
    expect(screen.getByText('production')).toBeInTheDocument()
  })

  it('accepts a variant without throwing', () => {
    render(<Badge variant="danger">rejected</Badge>)
    expect(screen.getByText('rejected')).toBeInTheDocument()
  })
})
