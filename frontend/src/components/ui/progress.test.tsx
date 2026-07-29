import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Progress } from '@/components/ui/progress'

describe('Progress', () => {
  it('exposes the current value via ARIA attributes', () => {
    render(<Progress value={40} max={100} label="Training progress" />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '40')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
    expect(bar).toHaveAttribute('aria-label', 'Training progress')
  })

  it('clamps values above max to 100%', () => {
    const { container } = render(<Progress value={150} max={100} />)
    const fill = container.querySelector('[style*="width"]') as HTMLElement
    expect(fill.style.width).toBe('100%')
  })

  it('clamps negative values to 0%', () => {
    const { container } = render(<Progress value={-10} max={100} />)
    const fill = container.querySelector('[style*="width"]') as HTMLElement
    expect(fill.style.width).toBe('0%')
  })
})
