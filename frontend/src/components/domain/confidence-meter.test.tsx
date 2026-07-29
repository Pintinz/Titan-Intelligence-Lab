import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfidenceMeter } from '@/components/domain/confidence-meter'
import type { ConfidenceBreakdownDto } from '@/lib/api/types'

const CONFIDENCE: ConfidenceBreakdownDto = {
  overall: 0.82,
  data_quality: 0.9,
  feature_completeness: 0.85,
  model_certainty: 0.8,
  historical_accuracy: 0.75,
  sample_size_adequacy: 0.7,
  market_liquidity: 0.6,
  temporal_relevance: 0.95,
  ensemble_agreement: 0.88,
  calibration_quality: 0.9,
  volatility_penalty: 0.3,
}

describe('ConfidenceMeter', () => {
  it('renders the overall confidence as a rounded percentage', () => {
    render(<ConfidenceMeter confidence={CONFIDENCE} />)
    expect(screen.getByText('82%')).toBeInTheDocument()
  })

  it('renders a row for every confidence factor', () => {
    render(<ConfidenceMeter confidence={CONFIDENCE} />)
    expect(screen.getByText('Data quality')).toBeInTheDocument()
    expect(screen.getByText('Volatility penalty')).toBeInTheDocument()
    expect(screen.getByText('Ensemble agreement')).toBeInTheDocument()
  })
})
