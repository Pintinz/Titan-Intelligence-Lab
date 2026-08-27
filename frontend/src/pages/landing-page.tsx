import { useEffect, useState } from 'react'
import { SiteHeader } from '@/components/layout/site-header'
import { SiteFooter } from '@/components/layout/site-footer'
import { Seo } from '@/components/seo/seo'
import { useLandingIntelligence } from '@/lib/hooks/use-landing-intelligence'
import { HeroSection } from './landing/hero-section'
import { FeaturedMatchSection } from './landing/featured-match-section'
import { VerifiedIntelligenceSection } from './landing/verified-intelligence-section'
import { MechanismPipelineSection } from './landing/mechanism-pipeline-section'
import { ExplainabilitySection } from './landing/explainability-section'
import { TrustDifferentiationSection } from './landing/trust-differentiation-section'
import { HowItWorksSection } from './landing/how-it-works-section'
import { SignalStripSection } from './landing/signal-strip-section'
import { TrustBadgesSection } from './landing/trust-badges-section'
import { MultiSportSection } from './landing/multi-sport-section'
import { NewsIntelligenceSection } from './landing/news-intelligence-section'
import { KnowledgeGraphSection } from './landing/knowledge-graph-section'
import { LearningIntelligenceSection } from './landing/learning-intelligence-section'
import { SubscriptionPlansSection } from './landing/subscription-plans-section'
import { FaqTeaserSection } from './landing/faq-teaser-section'
import { CtaSection } from './landing/cta-section'

export default function LandingPage() {
  const { loading, platformSummary, featuredIntelligence, verifiedIntelligence, newsIntelligence, knowledgeGraphPreview } =
    useLandingIntelligence()

  // The hero rotates through every real published pick TitanIQ currently has (already ranked and
  // time-diversified by featured-intelligence — LIVE, then genuinely-upcoming, then highest-
  // confidence; a completed fixture is excluded from this endpoint entirely — see "Verified
  // Intelligence" for those) instead of staying pinned to a single fixture for as long as the tab
  // stays open. Modulo, not a reset effect: safe against `featuredIntelligence.length` changing
  // under it (e.g. after the hook's own background refresh) without an extra effect to keep in sync.
  const [heroIndex, setHeroIndex] = useState(0)
  useEffect(() => {
    if (featuredIntelligence.length < 2) return
    const id = setInterval(() => setHeroIndex((i) => i + 1), 9000)
    return () => clearInterval(id)
  }, [featuredIntelligence.length])
  const topPick = featuredIntelligence.length > 0 ? featuredIntelligence[heroIndex % featuredIntelligence.length] : null

  return (
    <div className="min-h-svh bg-bg-primary">
      <Seo
        title="TitanIQ — Sports Intelligence Beyond Prediction"
        description="TitanIQ transforms live sports data, structured intelligence, news, and community signals into explainable sports intelligence across Football, Basketball, Baseball, and Table Tennis."
        path="/"
      />
      <SiteHeader />

      <div className="landing-intel">
        {/* 1. Hero */}
        <HeroSection loading={loading} pick={topPick} />

        {/* 2. Live Platform Activity */}
        <SignalStripSection loading={loading} summary={platformSummary} />

        {/* 3. Proof of Mechanism */}
        <FeaturedMatchSection loading={loading} picks={featuredIntelligence} />

        {/* 3b. Verified Intelligence — completed matches, predicted vs. actual */}
        <VerifiedIntelligenceSection loading={loading} picks={verifiedIntelligence} />

        {/* 4. How TitanIQ Works */}
        <HowItWorksSection />

        {/* 5. Trust badges */}
        <TrustBadgesSection />

        <MechanismPipelineSection />
        <ExplainabilitySection pick={topPick} />

        {/* 6. Trust & Differentiation */}
        <TrustDifferentiationSection />

        {/* 7. Multi-Sport Intelligence */}
        <MultiSportSection loading={loading} sports={platformSummary?.sports ?? []} />

        {/* 8. News / Knowledge Graph / Learning */}
        <NewsIntelligenceSection loading={loading} items={newsIntelligence} />
        <KnowledgeGraphSection loading={loading} preview={knowledgeGraphPreview} />
        <LearningIntelligenceSection />

        {/* 9. Subscription Plans */}
        <SubscriptionPlansSection />

        {/* 10. FAQ */}
        <FaqTeaserSection />

        {/* 11. Final CTA */}
        <CtaSection />
      </div>

      {/* 11. Footer */}
      <SiteFooter />
    </div>
  )
}
