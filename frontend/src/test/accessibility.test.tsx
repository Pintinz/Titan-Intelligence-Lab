import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { axe } from 'vitest-axe'
import { toHaveNoViolations } from 'vitest-axe/matchers'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { StatCard } from '@/components/domain/stat-card'
import { EmptyState } from '@/components/ui/empty-state'

expect.extend({ toHaveNoViolations })

describe('accessibility', () => {
  it('a labeled form field has no axe violations', async () => {
    const { container } = render(
      <div>
        <Label htmlFor="email">Email</Label>
        <Input id="email" type="email" />
      </div>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('a button + badge composition has no axe violations', async () => {
    const { container } = render(
      <div>
        <Button>Submit</Button>
        <Badge variant="success">production</Badge>
      </div>,
    )
    expect(await axe(container)).toHaveNoViolations()
  })

  it('a stat card has no axe violations', async () => {
    const { container } = render(<StatCard label="Sample size" value="128" />)
    expect(await axe(container)).toHaveNoViolations()
  })

  it('an empty state has no axe violations', async () => {
    const { container } = render(<EmptyState title="No results" description="Try a different filter." />)
    expect(await axe(container)).toHaveNoViolations()
  })
})
