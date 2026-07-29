import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Stepper } from '@/components/domain/stepper'

const STEPS = [
  { id: 'draft', label: 'Draft' },
  { id: 'review', label: 'Review' },
  { id: 'production', label: 'Production' },
]

describe('Stepper', () => {
  it('marks exactly one step with aria-current', () => {
    const { container } = render(<Stepper steps={STEPS} currentStepId="review" />)
    expect(container.querySelectorAll('[aria-current="step"]')).toHaveLength(1)
  })

  it('renders every step label', () => {
    render(<Stepper steps={STEPS} currentStepId="draft" />)
    for (const step of STEPS) {
      expect(screen.getByText(step.label)).toBeInTheDocument()
    }
  })
})
