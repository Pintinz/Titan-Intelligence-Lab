import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { SportShell } from './sport-shell'

function renderShell(path = '/app/football') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/:sport" element={<SportShell />}>
          <Route index element={<div>Child content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

describe('SportShell', () => {
  // InfinityAppShell's `main` (p-4 lg:p-6) already pads every /app/* page — SportShell used to
  // stack a second px-4/lg:px-8 (header) and p-4/lg:p-8 (outlet wrapper) on top of that, doubling
  // the mobile side margins on every Sport Intelligence Center page (32px wasted per side at
  // 375px width, including the match detail page). Guards against reintroducing that.
  it('does not apply its own horizontal padding around the header or the outlet content', () => {
    renderShell()

    const heading = screen.getByRole('heading', { name: 'Football' })
    const header = heading.closest('div')
    expect(header).not.toBeNull()
    expect(header!.className).not.toMatch(/(?:^|\s)(?:px|p)-\d/)

    const outletWrapper = screen.getByText('Child content').parentElement
    expect(outletWrapper).not.toBeNull()
    expect(outletWrapper!.className).not.toMatch(/(?:^|\s)(?:px|p)-\d/)
  })
})
