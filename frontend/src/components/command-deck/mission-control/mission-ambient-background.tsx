/**
 * MissionAmbientBackground — the layered ground Mission Control sits on: two soft indigo glow
 * blobs on a slow ambient breathe (reuses the existing `animate-hero-glow` keyframe from the Team
 * Hero stadium backdrop rather than inventing a near-duplicate) plus a very faint telemetry grid.
 * Purely decorative (`aria-hidden`, `pointer-events-none`), absolutely positioned behind the page
 * content, and reduced-motion safe. Never above `z-0` — content always reads first.
 */
export function MissionAmbientBackground() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden rounded-[inherit]" aria-hidden="true">
      <div
        className="animate-hero-glow motion-reduce:animate-none absolute -left-[10%] -top-[15%] h-[520px] w-[520px] rounded-full opacity-60"
        style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)' }}
      />
      <div
        className="animate-hero-glow motion-reduce:animate-none absolute -right-[8%] top-[25%] h-[440px] w-[440px] rounded-full opacity-40"
        style={{ background: 'radial-gradient(circle, var(--cd-accent-muted) 0%, transparent 70%)', animationDelay: '2.5s' }}
      />
      <div
        className="animate-hero-glow motion-reduce:animate-none absolute bottom-[5%] left-[35%] h-[400px] w-[400px] rounded-full opacity-30"
        style={{ background: 'radial-gradient(circle, var(--cd-positive-muted) 0%, transparent 72%)', animationDelay: '5s' }}
      />
      <div
        className="absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            'linear-gradient(var(--cd-text-primary) 1px, transparent 1px), linear-gradient(90deg, var(--cd-text-primary) 1px, transparent 1px)',
          backgroundSize: '56px 56px',
          maskImage: 'radial-gradient(ellipse 80% 60% at 50% 0%, black 0%, transparent 70%)',
          WebkitMaskImage: 'radial-gradient(ellipse 80% 60% at 50% 0%, black 0%, transparent 70%)',
        }}
      />
    </div>
  )
}
