import { useEffect, useState } from 'react'

/** Real-derived ambient tint, sampled from a team's own crest — not a hardcoded club-color
 * table. Most teams in this app aren't real clubs (basketball/baseball/table-tennis are
 * generated mock rosters), so a curated palette would be meaningless for most and arbitrary for
 * the rest; sampling each team's actual artwork scales honestly to every team. Falls back to the
 * given fallback tone when there's no crest, it hasn't loaded, or the provider host doesn't send
 * CORS headers (canvas pixel reads throw in that case — a real, expected failure mode for
 * third-party images, caught silently rather than surfaced as an error state). */
export function useCrestAccentColor(logoUrl: string | null | undefined, fallback: string): string {
  const [color, setColor] = useState(fallback)

  useEffect(() => {
    setColor(fallback)
    if (!logoUrl) return
    let cancelled = false
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      if (cancelled) return
      try {
        const size = 24
        const canvas = document.createElement('canvas')
        canvas.width = size
        canvas.height = size
        const ctx = canvas.getContext('2d')
        if (!ctx) return
        ctx.drawImage(img, 0, 0, size, size)
        const { data } = ctx.getImageData(0, 0, size, size)
        let r = 0
        let g = 0
        let b = 0
        let n = 0
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 3] < 128) continue
          const lum = (data[i] + data[i + 1] + data[i + 2]) / 3
          // Skip near-white/near-black pixels — usually crest padding or an outline stroke,
          // not the club's actual identifying color.
          if (lum > 235 || lum < 20) continue
          r += data[i]
          g += data[i + 1]
          b += data[i + 2]
          n++
        }
        if (n === 0 || cancelled) return
        const toHex = (v: number) => Math.round(v / n).toString(16).padStart(2, '0')
        setColor(`#${toHex(r)}${toHex(g)}${toHex(b)}`)
      } catch {
        // Cross-origin crest without CORS headers taints the canvas — expected, not an error.
      }
    }
    img.src = logoUrl
    return () => {
      cancelled = true
    }
  }, [logoUrl, fallback])

  return color
}
