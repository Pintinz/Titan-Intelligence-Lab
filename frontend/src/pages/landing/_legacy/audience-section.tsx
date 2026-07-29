/** Replaces fabricated "customer logos" (no real customers exist) with the real target
 * personas already named in the product brief — no invented company names. */
const AUDIENCES = [
  'Professional analysts',
  'Sports clubs',
  'Researchers',
  'Investors',
  'Data scientists',
  'Sports media',
  'Fantasy professionals',
  'Serious sports enthusiasts',
]

export function AudienceSection() {
  return (
    <section className="border-y border-border-subtle bg-bg-secondary px-6 py-14">
      <div className="mx-auto max-w-4xl text-center">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Built for</p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
          {AUDIENCES.map((audience) => (
            <span key={audience} className="text-sm font-medium text-text-secondary">
              {audience}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}
