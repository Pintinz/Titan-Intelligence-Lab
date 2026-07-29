import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusDot } from '@/components/ui/status-dot'

describe('StatusDot', () => {
  it('renders a label when given', () => {
    render(<StatusDot tone="success" label="healthy" />)
    expect(screen.getByText('healthy')).toBeInTheDocument()
  })

  it('renders without a label', () => {
    const { container } = render(<StatusDot tone="danger" />)
    expect(container.querySelector('span')).toBeTruthy()
  })
})
