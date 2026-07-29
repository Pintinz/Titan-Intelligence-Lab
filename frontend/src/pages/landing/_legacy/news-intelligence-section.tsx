import { motion } from 'framer-motion'
import { Badge } from '@/components/ui/badge'
import { SAMPLE_NEWS } from '@/pages/landing/sample-data'
import { staggerContainer, staggerItem } from '@/lib/motion'

const SENTIMENT_VARIANT = { positive: 'success', neutral: 'neutral', negative: 'danger' } as const

export function NewsIntelligenceSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="news">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">News, turned into intelligence</h2>
        <p className="mt-3 text-text-secondary">
          Every article is summarized, scored for sentiment and source reliability, and linked to the
          entities it affects — not just a headline feed.
        </p>
      </div>

      <motion.div
        variants={staggerContainer}
        initial="initial"
        whileInView="animate"
        viewport={{ once: true, margin: '-80px' }}
        className="-mx-1 mt-10 flex gap-6 overflow-x-auto px-1 pb-2 [scrollbar-width:none] sm:grid sm:overflow-visible sm:px-0 sm:pb-0 sm:grid-cols-2 lg:grid-cols-3 [&::-webkit-scrollbar]:hidden"
      >
        {SAMPLE_NEWS.map((article) => (
          <motion.div
            key={article.title}
            variants={staggerItem}
            whileHover={{ y: -4 }}
            className="flex w-72 shrink-0 flex-col gap-3 rounded-lg border border-border-default bg-bg-elevated p-5 shadow-[var(--shadow-elevation-1)] transition-shadow hover:shadow-[var(--shadow-elevation-3)] sm:w-auto"
          >
            <div className="flex items-center justify-between">
              <Badge variant={SENTIMENT_VARIANT[article.sentiment]}>{article.sentiment}</Badge>
              <span className="font-mono text-xs text-text-muted">reliability {Math.round(article.reliability * 100)}%</span>
            </div>
            <p className="font-display text-sm font-semibold text-text-primary">{article.title}</p>
            <p className="text-sm text-text-secondary">{article.aiSummary}</p>
            <div className="flex flex-wrap gap-1.5">
              {article.relatedEntities.map((entity) => (
                <span key={entity} className="rounded-full border border-border-default bg-bg-secondary px-2 py-0.5 text-[11px] text-text-secondary">
                  {entity}
                </span>
              ))}
            </div>
          </motion.div>
        ))}
      </motion.div>

      <p className="mt-6 text-center text-xs text-text-muted">Illustrative — AI summaries and sentiment are real capabilities of the News Center, shown here with sample articles.</p>
    </section>
  )
}
