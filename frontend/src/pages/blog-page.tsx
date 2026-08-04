import { Seo } from '@/components/seo/seo'
import { Section } from '@/pages/landing/section-primitives'
import { PageHero } from '@/components/marketing/marketing-primitives'

const POSTS = [
  {
    title: 'Why we show confidence, not certainty',
    date: 'July 14, 2026',
    category: 'Product',
    body: 'Most prediction products hide their uncertainty behind a confident tone. We built TitanIQ the opposite way: every prediction ships with a calibrated confidence score, and we treat a well-calibrated 55% as more valuable than a persuasive 95% that isn\'t earned. This post walks through why calibration — not raw accuracy — is the metric we optimize for, and what that looks like in the Learning Intelligence pipeline that recalibrates our models after every match.',
  },
  {
    title: 'Table Tennis Intelligence is live',
    date: 'June 2, 2026',
    category: 'Launch',
    body: 'Table Tennis joins Football, Basketball, and Baseball as TitanIQ\'s fourth Sport Intelligence Center. Table tennis presented a genuinely different modeling problem — shorter matches, faster momentum swings, and a much thinner public-data landscape than the major team sports. We rebuilt our feature pipeline around point-by-point momentum and head-to-head history rather than season-long form, and it shows in how differently the Table Tennis confidence bands behave compared to football.',
  },
  {
    title: 'Inside the Knowledge Graph',
    date: 'May 19, 2026',
    category: 'Engineering',
    body: 'Predictions are the visible output, but the Knowledge Graph is the structure underneath them — teams, players, competitions, and venues, connected by relationships that explain, not just correlate. When a player is ruled out, the graph is what lets the model reason about the specific tactical role that absence leaves open, instead of treating "missing a player" as one undifferentiated signal.',
  },
  {
    title: 'What Community Pulse actually measures',
    date: 'April 8, 2026',
    category: 'Methodology',
    body: 'Community Pulse aggregates sentiment and signal volume from users engaging with a match on TitanIQ — it is one input among many, weighted modestly, and it never overrides the evidence-based model output. This post explains why we included it at all, how we guard against it amplifying crowd bias rather than informing it, and where you can see its contribution on a match\'s evidence panel.',
  },
]

export default function BlogPage() {
  return (
    <>
      <Seo
        title="Blog"
        description="Product updates and intelligence notes from the team building TitanIQ."
        path="/blog"
      />
      <PageHero
        eyebrow="Blog"
        title="Notes from the intelligence team."
        description="Product updates, methodology deep-dives, and what we've learned building an explainable sports-intelligence platform."
      />

      <Section className="max-w-3xl space-y-10">
        {POSTS.map((post) => (
          <article key={post.title} className="border-b border-border-subtle pb-10 last:border-0 last:pb-0">
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span className="font-medium uppercase tracking-wide text-accent-primary">{post.category}</span>
              <span aria-hidden="true">·</span>
              <time>{post.date}</time>
            </div>
            <h2 className="mt-2 font-display text-xl font-semibold text-text-primary">{post.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-text-secondary">{post.body}</p>
          </article>
        ))}
      </Section>
    </>
  )
}
