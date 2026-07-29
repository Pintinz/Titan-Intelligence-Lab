import type { Transition, Variants } from 'framer-motion'

/**
 * Shared framer-motion primitives, kept in numeric sync with the CSS motion tokens in
 * src/styles/tokens.css (`--motion-duration-*`/`--motion-easing-*`) — framer-motion's
 * `transition` prop needs real numbers/arrays, not CSS custom properties, so these are
 * duplicated by hand rather than read at runtime. If the CSS tokens change, update these too.
 */
export const DURATION = {
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
} as const

export const EASING = {
  standard: [0.4, 0, 0.2, 1],
  decelerate: [0, 0, 0.2, 1],
  accelerate: [0.4, 0, 1, 1],
} as const

export const transitionBase: Transition = { duration: DURATION.base, ease: EASING.standard }
export const transitionSlow: Transition = { duration: DURATION.slow, ease: EASING.decelerate }
export const transitionFast: Transition = { duration: DURATION.fast, ease: EASING.accelerate }

/** Page-level entrance — fade + small upward drift, used by route-level page wrappers. */
export const pageTransition: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: transitionBase },
  exit: { opacity: 0, y: -8, transition: transitionFast },
}

/** Card hover — subtle lift, no scale (scale-on-hover reads as "clickable toy", not enterprise). */
export const cardHover = {
  rest: { y: 0, boxShadow: 'var(--shadow-elevation-1)' },
  hover: { y: -2, boxShadow: 'var(--shadow-elevation-2)', transition: transitionFast },
}

/** Stagger container for lists/grids of cards entering together. */
export const staggerContainer: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.05 } },
}

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: transitionBase },
}
