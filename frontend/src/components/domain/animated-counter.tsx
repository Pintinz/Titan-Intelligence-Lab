import { useRef } from 'react'
import { motion, useMotionValue, useTransform, animate } from 'framer-motion'

/** Count-up number that animates once when scrolled into view — uses framer-motion's own
 * `onViewportEnter` (rather than a separately-wired useInView + useEffect) since that's the
 * primitive already guaranteed to compose correctly with animate()/motion values. */
export function AnimatedCounter({ value, duration = 1.4 }: { value: number; duration?: number }) {
  const hasAnimated = useRef(false)
  const motionValue = useMotionValue(0)
  const rounded = useTransform(motionValue, (latest) => Math.round(latest).toLocaleString())

  return (
    <motion.span
      viewport={{ once: true, margin: '-80px' }}
      onViewportEnter={() => {
        if (hasAnimated.current) return
        hasAnimated.current = true
        animate(motionValue, value, { duration, ease: [0, 0, 0.2, 1] })
      }}
    >
      {rounded}
    </motion.span>
  )
}
