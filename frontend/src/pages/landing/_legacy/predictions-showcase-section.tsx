import { useState } from 'react'
import { motion } from 'framer-motion'
import { PredictionCard } from '@/components/domain/prediction-card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { SAMPLE_PREDICTIONS, SAMPLE_PREDICTIONS_BY_SPORT } from '@/pages/landing/sample-data'
import { SPORT_OPTIONS } from '@/lib/api/sports'
import { staggerContainer, staggerItem } from '@/lib/motion'

export function PredictionsShowcaseSection() {
  const [sport, setSport] = useState('all')
  const predictions = sport === 'all' ? SAMPLE_PREDICTIONS : (SAMPLE_PREDICTIONS_BY_SPORT[sport] ?? [])

  return (
    <section className="mx-auto max-w-6xl px-6 py-20" id="predictions">
      <div className="mx-auto max-w-2xl text-center">
        <h2 className="font-display text-3xl font-semibold text-text-primary">Today's AI predictions</h2>
        <p className="mt-3 text-text-secondary">
          Calibrated, explainable predictions across every sport TitanIQ covers — the same
          card every signed-in user sees in the Prediction Center.
        </p>
      </div>

      <Tabs value={sport} onValueChange={setSport} className="mt-8">
        <TabsList className="mx-auto w-fit">
          <TabsTrigger value="all">All sports</TabsTrigger>
          {SPORT_OPTIONS.map((option) => (
            <TabsTrigger key={option.code} value={option.code}>
              {option.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={sport}>
          <motion.div
            variants={staggerContainer}
            initial="initial"
            animate="animate"
            className="-mx-1 mt-8 flex gap-4 overflow-x-auto px-1 pb-2 [scrollbar-width:none] sm:grid sm:gap-4 sm:overflow-visible sm:px-0 sm:pb-0 sm:grid-cols-2 lg:grid-cols-3 [&::-webkit-scrollbar]:hidden"
          >
            {predictions.map((prediction) => (
              <motion.div key={prediction.id} variants={staggerItem} whileHover={{ y: -4 }} className="w-80 shrink-0 sm:w-auto">
                <PredictionCard prediction={prediction} />
              </motion.div>
            ))}
          </motion.div>
        </TabsContent>
      </Tabs>

      <p className="mt-6 text-center text-xs text-text-muted">
        Illustrative preview — sign in to see live predictions for real fixtures in the Prediction Center.
      </p>
    </section>
  )
}
