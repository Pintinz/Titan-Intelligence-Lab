import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})

// jsdom doesn't implement matchMedia — several components (prefers-reduced-motion checks,
// Radix internals) read it defensively, so provide a minimal stub rather than letting every
// test that touches them fail on an unrelated ReferenceError.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
})

// jsdom doesn't implement the Pointer Events capture API or scrollIntoView — Radix Select's
// internals call these on open/close regardless of environment, so every test that interacts
// with a Select would otherwise throw a TypeError unrelated to the thing being tested.
Element.prototype.hasPointerCapture ??= () => false
Element.prototype.setPointerCapture ??= () => {}
Element.prototype.releasePointerCapture ??= () => {}
Element.prototype.scrollIntoView ??= () => {}
