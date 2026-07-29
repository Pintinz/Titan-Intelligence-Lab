import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tag } from '@/components/ui/tag'

describe('Tag', () => {
  it('renders its label', () => {
    render(<Tag>football</Tag>)
    expect(screen.getByText('football')).toBeInTheDocument()
  })

  it('omits the remove button when no handler is given', () => {
    render(<Tag>football</Tag>)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('calls onRemove when the remove button is clicked', async () => {
    const onRemove = vi.fn()
    render(<Tag onRemove={onRemove}>football</Tag>)
    await userEvent.click(screen.getByRole('button', { name: 'Remove' }))
    expect(onRemove).toHaveBeenCalledOnce()
  })
})
