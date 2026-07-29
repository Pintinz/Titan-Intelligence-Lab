import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KeyValueGrid } from '@/components/domain/key-value-grid'

describe('KeyValueGrid', () => {
  it('renders each entry as a formatted label/value row', () => {
    render(<KeyValueGrid data={{ sample_size: 120, average_probability: 0.6543 }} />)
    expect(screen.getByText('Sample Size')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('Average Probability')).toBeInTheDocument()
    expect(screen.getByText('0.654')).toBeInTheDocument()
  })

  it('renders a null value as an em dash', () => {
    render(<KeyValueGrid data={{ reliability_score: null }} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('shows an empty message for an empty object', () => {
    render(<KeyValueGrid data={{}} />)
    expect(screen.getByText('No data available.')).toBeInTheDocument()
  })
})
