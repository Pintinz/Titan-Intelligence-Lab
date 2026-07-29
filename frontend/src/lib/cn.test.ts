import { describe, expect, it } from 'vitest'
import { cn } from '@/lib/cn'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('a', 'b')).toBe('a b')
  })

  it('drops falsy values', () => {
    expect(cn('a', false && 'b', undefined, null, 'c')).toBe('a c')
  })

  it('resolves conflicting tailwind utilities, keeping the last', () => {
    expect(cn('flex-col', 'flex-row')).toBe('flex-row')
  })

  it('resolves conflicting padding utilities', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4')
  })
})
