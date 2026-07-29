import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfidenceRing } from '@/components/domain/confidence-ring'

describe('ConfidenceRing', () => {
  it('renders the rounded percentage', () => {
    render(<ConfidenceRing value={0.78} />)
    expect(screen.getByText('78%')).toBeInTheDocument()
  })

  it('exposes an accessible label with the percentage', () => {
    render(<ConfidenceRing value={0.5} label="Confidence" />)
    expect(screen.getByRole('img', { name: 'Confidence: 50%' })).toBeInTheDocument()
  })

  it('clamps out-of-range values into 0-100%', () => {
    render(<ConfidenceRing value={1.4} />)
    expect(screen.getByText('100%')).toBeInTheDocument()
  })
})
