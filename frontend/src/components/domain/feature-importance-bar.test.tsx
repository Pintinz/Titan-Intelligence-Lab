import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { FeatureImportanceBars } from '@/components/domain/feature-importance-bar'

describe('FeatureImportanceBars', () => {
  it('renders both positive and negative feature lists', () => {
    render(
      <FeatureImportanceBars
        positive={[{ feature_key: 'team.form_index', contribution: 0.42 }]}
        negative={[{ feature_key: 'team.injury_count', contribution: -0.31 }]}
      />,
    )
    expect(screen.getByText('team.form_index')).toBeInTheDocument()
    expect(screen.getByText('team.injury_count')).toBeInTheDocument()
    expect(screen.getByText('0.420')).toBeInTheDocument()
    expect(screen.getByText('-0.310')).toBeInTheDocument()
  })

  it('shows "None" for an empty side rather than an empty list', () => {
    render(<FeatureImportanceBars positive={[]} negative={[]} />)
    expect(screen.getAllByText('None')).toHaveLength(2)
  })
})
