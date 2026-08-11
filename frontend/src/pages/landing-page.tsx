import { SiteHeader } from '@/components/layout/site-header'
import { SiteFooter } from '@/components/layout/site-footer'
import { Seo } from '@/components/seo/seo'
import { useLandingIntelligence } from '@/lib/hooks/use-landing-intelligence'
import { HeroSection } from './landing/hero-section'
import { SignalStripSection } from './landing/signal-strip-section'
import { FeaturedMatchSection } from './landing/featured-match-section'
import { MultiSportSection } from './landing/multi-sport-section'
import { NewsIntelligenceSection } from './landing/news-intelligence-section'
import { KnowledgeGraphSection } from './landing/knowledge-graph-section'
import { ExplainabilitySection } from './landing/explainability-section'
import { HowItWorksSection } from './landing/how-it-works-section'
import { LearningIntelligenceSection } from './landing/learning-intelligence-section'
import { CtaSection } from './landing/cta-section'

export default function LandingPage() {
  const { loading, platformSummary, featuredIntelligence, newsIntelligence, knowledgeGraphPreview } =
    useLandingIntelligence()
  const topPick = featuredIntelligence[0] ?? null

  return (
    <div className="min-h-svh bg-bg-primary">
      <Seo
        title="TitanIQ — Sports Intelligence Beyond Prediction"
        description="TitanIQ transforms live sports data, structured intelligence, news, and community signals into explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis."
        path="/"
      />
      <SiteHeader />
      <HeroSection loading={loading} pick={topPick} />
      <SignalStripSection loading={loading} summary={platformSummary} />
      <FeaturedMatchSection loading={loading} picks={featuredIntelligence} />
      <MultiSportSection loading={loading} sports={platformSummary?.sports ?? []} />
      <NewsIntelligenceSection loading={loading} items={newsIntelligence} />
      <KnowledgeGraphSection loading={loading} preview={knowledgeGraphPreview} />
      <ExplainabilitySection pick={topPick} />
      <HowItWorksSection />
      <LearningIntelligenceSection />
      <CtaSection />
      <SiteFooter />
    </div>
  )
}
