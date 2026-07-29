import type { ReactNode } from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { Dialog, DialogTrigger } from '@/components/ui/dialog'
import { ConfidenceMeter } from '@/components/domain/confidence-meter'
import { FeatureImportanceBars } from '@/components/domain/feature-importance-bar'
import type { ConfidenceBreakdownDto, ExplanationBundleDto } from '@/lib/api/types'
import { transitionBase } from '@/lib/motion'

/**
 * Slide-over presentation of the same ConfidenceBreakdownDto/ExplanationBundleDto data already
 * shown inline in PredictionCard's accordion — an alternate, deeper-focus layout for the flagship
 * Match Detail page, not new data or new business logic.
 */
export function ExplanationDrawer({
  confidence,
  explanation,
  trigger,
  open,
  onOpenChange,
}: {
  confidence: ConfidenceBreakdownDto
  explanation: ExplanationBundleDto
  trigger: ReactNode
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogPrimitive.Portal>
        <AnimatePresence>
          {open && (
            <>
              <DialogPrimitive.Overlay asChild forceMount>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={transitionBase}
                  className="fixed inset-0 z-50 bg-bg-overlay"
                />
              </DialogPrimitive.Overlay>
              <DialogPrimitive.Content asChild forceMount>
                <motion.div
                  initial={{ x: '100%' }}
                  animate={{ x: 0 }}
                  exit={{ x: '100%' }}
                  transition={transitionBase}
                  className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-border-default bg-bg-elevated shadow-[var(--shadow-elevation-3)] focus-visible:outline-none"
                >
                  <div className="flex items-center justify-between border-b border-border-subtle p-6">
                    <DialogPrimitive.Title className="font-display text-lg font-semibold text-text-primary">
                      AI Explanation
                    </DialogPrimitive.Title>
                    <DialogPrimitive.Close className="rounded-md p-1 text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary">
                      <X className="h-4 w-4" />
                      <span className="sr-only">Close</span>
                    </DialogPrimitive.Close>
                  </div>
                  <div className="flex-1 overflow-y-auto p-6">
                    <DialogPrimitive.Description className="sr-only">
                      Confidence breakdown and feature-level explanation for this prediction.
                    </DialogPrimitive.Description>
                    <ConfidenceMeter confidence={confidence} />
                    <div className="mt-6 border-t border-border-subtle pt-6">
                      <FeatureImportanceBars positive={explanation.top_positive_features} negative={explanation.top_negative_features} />
                    </div>
                    {(explanation.knowledge_graph_contribution ||
                      explanation.news_contribution ||
                      explanation.community_contribution ||
                      explanation.ai_explanation) && (
                      <div className="mt-6 flex flex-col gap-4 border-t border-border-subtle pt-6">
                        {explanation.ai_explanation && <Snippet label="Narrative" text={explanation.ai_explanation} />}
                        {explanation.knowledge_graph_contribution && (
                          <Snippet label="Knowledge Graph evidence" text={explanation.knowledge_graph_contribution} />
                        )}
                        {explanation.news_contribution && <Snippet label="News contribution" text={explanation.news_contribution} />}
                        {explanation.community_contribution && (
                          <Snippet label="Community contribution" text={explanation.community_contribution} />
                        )}
                      </div>
                    )}
                  </div>
                </motion.div>
              </DialogPrimitive.Content>
            </>
          )}
        </AnimatePresence>
      </DialogPrimitive.Portal>
    </Dialog>
  )
}

function Snippet({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <span className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</span>
      <p className="mt-1 text-sm text-text-secondary">{text}</p>
    </div>
  )
}
