import { useState } from 'react'
import { motion } from 'framer-motion'
import { KnowledgeGraphViewer } from '@/components/domain/knowledge-graph-viewer'
import { SAMPLE_KG_CENTER, SAMPLE_KG_NEIGHBORS, SAMPLE_KG_EDGES } from '@/pages/landing/sample-data'
import { transitionSlow } from '@/lib/motion'
import type { KgNodeDto } from '@/lib/api/types'

const EDGE_TYPES = Array.from(new Set(SAMPLE_KG_EDGES.map((e) => e.edge_type)))

export function KnowledgeGraphPreviewSection() {
  const [selected, setSelected] = useState<KgNodeDto | null>(null)

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="knowledge-graph">
      <div className="mx-auto max-w-2xl text-center">
        <span className="font-mono text-xs uppercase tracking-[0.2em] text-text-muted">Knowledge graph</span>
        <h2 className="mt-2 font-display text-3xl font-semibold text-text-primary">
          Every prediction is grounded in a graph
        </h2>
        <p className="mt-3 text-text-secondary">
          Teams, players, competitions, venues, and news connect into one queryable graph — scroll
          to zoom, click a node to inspect it. The real Graph Explorer works identically, on live data.
        </p>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
        transition={transitionSlow}
        className="mt-10 grid gap-4 lg:grid-cols-[1fr_220px]"
      >
        <div className="rounded-lg border border-border-default bg-bg-elevated p-4 shadow-[var(--shadow-elevation-1)]">
          <KnowledgeGraphViewer
            centerNode={SAMPLE_KG_CENTER}
            neighbors={SAMPLE_KG_NEIGHBORS}
            edges={SAMPLE_KG_EDGES}
            onNodeClick={setSelected}
            height={420}
          />
        </div>
        <div className="flex flex-col gap-4">
          <div>
            <span className="text-xs font-medium uppercase tracking-wide text-text-muted">Relationship types</span>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {EDGE_TYPES.map((type) => (
                <span key={type} className="rounded-full border border-border-default bg-bg-secondary px-2 py-0.5 font-mono text-[11px] text-text-secondary">
                  {type}
                </span>
              ))}
            </div>
          </div>
          {selected && (
            <div className="rounded-md border border-border-subtle bg-bg-secondary/50 p-3">
              <p className="text-sm font-medium text-text-primary">{selected.entity_ref}</p>
              <p className="text-xs text-text-muted">{selected.node_type}</p>
            </div>
          )}
        </div>
      </motion.div>

      <p className="mt-4 text-center text-xs text-text-muted">
        Illustrative preview — real entity counts and relationships require a signed-in session.
      </p>
    </section>
  )
}
